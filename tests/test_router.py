# coding: utf-8

import unittest
from signal import SIGINT, SIGKILL
from time import sleep
from subprocess import Popen, PIPE
from utils import default_config
import shlex
import zmq


#TODO: validate pipeline data when requested
time_to_wait = 150

class TestRouter(unittest.TestCase):
    def setUp(self):
        self.context = zmq.Context()
        self.start_router_process()
        self.api = self.context.socket(zmq.REQ)
        self.api.connect('tcp://localhost:5555')
        self.broadcast = self.context.socket(zmq.SUB)
        self.broadcast.connect('tcp://localhost:5556')
        self.broadcast.setsockopt(zmq.SUBSCRIBE, 'new job')

    def tearDown(self):
        self.end_router_process()
        self.close_sockets()
        self.context.term()

    def start_router_process(self):
        self.router = Popen(shlex.split('python ./tests/my_router.py'),
                             stdin=PIPE, stdout=PIPE, stderr=PIPE)
        for line in self.router.stdout.readline():
            if 'main loop' in line:
                break

    def end_router_process(self):
        self.router.send_signal(SIGINT)
        sleep(time_to_wait / 1000.0)
        self.router.send_signal(SIGKILL)
        self.router.wait()

    def close_sockets(self):
        self.api.close()
        self.broadcast.close()

    def test_connect_to_router_api_zmq_socket_and_execute_undefined_command(self):
        self.api.send_json({'spam': 'eggs'})
        if not self.api.poll(time_to_wait):
            self.fail("Didn't receive 'undefined command' from router")
        message = self.api.recv_json()
        self.assertEqual(message, {'answer': 'undefined command'})

    def test_should_connect_to_router_api_zmq_socket(self):
        self.api.send_json({'command': 'hello'})
        if not self.api.poll(time_to_wait):
            self.fail("Didn't receive 'unknown command' from router")
        message = self.api.recv_json()
        self.assertEqual(message, {'answer': 'unknown command'})

    def test_should_receive_new_job_from_broadcast_when_a_job_is_submitted(self):
        self.api.send_json({'command': 'add job', 'worker': 'x',
                            'data': 'y'})
        if not self.api.poll(time_to_wait):
            self.fail("Didn't receive 'add job' reply")
        self.api.recv_json()
        if not self.broadcast.poll(time_to_wait):
            self.fail("Didn't receive 'new job' from broadcast")
        message = self.broadcast.recv()
        self.assertEqual(message, 'new job')

    def test_command_get_configuration_should_return_dict_passed_on_setUp(self):
        self.api.send_json({'command': 'get configuration'})
        if not self.api.poll(time_to_wait):
            self.fail("Didn't receive configuration from router")
        message = self.api.recv_json()
        self.assertEqual(message, default_config)

    def test_command_add_job_should_return_a_job_id(self):
        cmd = {'command': 'add job', 'worker': 'test', 'data': 'eggs'}
        self.api.send_json(cmd)
        if not self.api.poll(time_to_wait):
            self.fail("Didn't receive 'job accepted' from router")
        message = self.api.recv_json()
        self.assertEqual(message['answer'], 'job accepted')
        self.assertIn('job id', message)
        self.assertEqual(len(message['job id']), 32)

    def test_command_get_job_should_return_empty_if_no_job(self):
        self.api.send_json({'command': 'get job'})
        if not self.api.poll(time_to_wait):
            self.fail("Didn't receive job (None) from router")
        message = self.api.recv_json()
        self.assertEqual(message['worker'], None)

    def test_command_get_job_should_return_a_job_after_adding_one(self):
        self.api.send_json({'command': 'add job', 'worker': 'spam',
                            'data': 'eggs'})
        if not self.api.poll(time_to_wait):
            self.fail("Didn't receive 'add job' reply")
        job = self.api.recv_json()
        self.api.send_json({'command': 'get job'})
        if not self.api.poll(time_to_wait):
            self.fail("Didn't receive job from router")
        message = self.api.recv_json()
        self.assertEqual(message['worker'], 'spam')
        self.assertEqual(message['data'], 'eggs')
        self.assertIn('job id', message)
        self.assertEqual(len(message['job id']), 32)

    def test_finished_job_without_job_id_should_return_error(self):
        self.api.send_json({'command': 'job finished'})
        if not self.api.poll(time_to_wait):
            self.fail("Didn't receive 'syntax error' from router")
        message = self.api.recv_json()
        self.assertEqual(message['answer'], 'syntax error')

    def test_finished_job_with_unknown_job_id_should_return_error(self):
        self.api.send_json({'command': 'job finished', 'job id': 'python rlz',
                            'duration': 0.1})
        if not self.api.poll(time_to_wait):
            self.fail("Didn't receive 'unknown job id' from router")
        message = self.api.recv_json()
        self.assertEqual(message['answer'], 'unknown job id')

    def test_finished_job_with_correct_job_id_should_return_good_job(self):
        self.api.send_json({'command': 'add job', 'worker': 'a',
                            'data': 'b'})
        if not self.api.poll(time_to_wait):
            self.fail("Didn't receive 'add job' reply")
        message = self.api.recv_json()
        self.api.send_json({'command': 'job finished',
                            'job id': message['job id'],
                            'duration': 0.1})
        if not self.api.poll(time_to_wait):
            self.fail("Didn't receive 'good job!' from router. "
                      "#foreveralone :-(")
        message = self.api.recv_json()
        self.assertEqual(message['answer'], 'good job!')

    def test_should_receive_job_finished_message_with_job_id_and_duration_when_a_job_finishes(self):
        self.api.send_json({'command': 'add job', 'worker': 'x',
                            'data': 'y'})
        if not self.api.poll(time_to_wait):
            self.fail("Didn't receive 'add job' reply")
        self.api.recv_json()
        if not self.broadcast.poll(time_to_wait):
            self.fail("Didn't receive 'new job' from broadcast")
        message = self.broadcast.recv()
        self.assertEqual(message, 'new job')
        self.api.send_json({'command': 'get job'})
        if not self.api.poll(time_to_wait):
            self.fail("Didn't receive 'get job' reply")
        job = self.api.recv_json()
        self.broadcast.setsockopt(zmq.SUBSCRIBE,
                                  'job finished: {}'.format(job['job id']))
        del job['worker']
        job['command'] = 'job finished'
        job['duration'] = 0.1
        self.api.send_json(job)
        if not self.broadcast.poll(time_to_wait):
            self.fail("Didn't receive 'new job' from broadcast")
        message = self.broadcast.recv()
        expected = 'job finished: {} duration: 0.1'.format(job['job id'])
        self.assertEqual(message, expected)

    #TODO: create tests for pipelines
