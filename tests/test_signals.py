from unittest import TestCase
import random

from pytia import *

class TestSignal(TestCase):

    def signal1_callback(self, id):
        # just send back fixed values for each channel
        return range(self.num_channels)

    def signal2_callback(self, id):
        # just send back fixed values for each channel
        return self.random_vals

    def setUp(self):
        self.num_channels = random.randint(1, 5)
        self.random_vals = [random.randint(1, 100) for x in range(self.num_channels)]
        self.port = random.randint(9000, 10000)

        # start a pytia server instance 
        self.server = TiAServer(('', self.port), TiAConnectionHandler)

        # configure the server with a couple of signals
        self.signal1 = TiASignalConfig(channels=self.num_channels, sample_rate=10, blocksize=1, callback=self.signal1_callback, id=1, is_master=True, sigtype=TIA_SIG_USER_1)
        self.signal2 = TiASignalConfig(channels=self.num_channels, sample_rate=10, blocksize=1, callback=self.signal2_callback, id=2, is_master=False, sigtype=TIA_SIG_USER_2)
        self.server.start([self.signal1, self.signal2], single_shot=True)

    def tearDown(self):
        pass 

    def test_basic(self):
        # check if the signal channel values come through as expected...

        client = TiAClient('127.0.0.1', self.port)
        result = client.connect()
        self.assertEqual(result, True)

        result = client.cmd_check_protocol_version()
        self.assertEqual(result, True)

        status, dport = client.cmd_get_data_connection_tcp()
        self.assertEqual(status, True)
        self.assertGreater(dport, 0)

        result = client.start_streaming_data_tcp('127.0.0.1', dport)
        self.assertEqual(result, True)

        packets = client.get_data()
        # expecting a single packet
        self.assertEqual(len(packets), 1) 

        packet = packets[0]
        # expecting the packet to contain 2 signals
        self.assertEqual(len(packet.signals), 2)

        # expecting each signal to contain num_channels values
        for i in range(2):
            self.assertEqual(packet.channels[i], self.num_channels)

        data1 = packet.get_channel(0)
        data2 = packet.get_channel(1)

        # first channel should have increasing integers as data values
        for i in range(self.num_channels):
            self.assertEqual(data1[i], i)

        # second channel should match self.random_vals
        for i in range(self.num_channels):
            self.assertEqual(data2[i], self.random_vals[i])

        client.stop_streaming_data()
        client.disconnect()
