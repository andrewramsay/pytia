# -*- coding: utf-8 -*-
import struct, socket, threading, time, random
from SocketServer import BaseRequestHandler, ThreadingMixIn, TCPServer

# Signal types defined by TOBI interface A
TIA_SIG_EEG         = 0x00000001        # Electroencephalogram
TIA_SIG_EMG         = 0x00000002        # Electromyogram
TIA_SIG_EOG         = 0x00000004        # Electrooculugram 
TIA_SIG_ECG         = 0x00000008        # Electrocardiogram
TIA_SIG_HR          = 0x00000010        # Heart rate
TIA_SIG_BP          = 0x00000020        # Blood pressure
TIA_SIG_BUTTON      = 0x00000040        # Buttons (aperiodic)
TIA_SIG_JOYSTICK    = 0x00000080        # Joystick axis (aperiodic)
TIA_SIG_SENSORS     = 0x00000100        # Sensor
TIA_SIG_NIRS        = 0x00000200        # NIRS
TIA_SIG_FMRI        = 0x00000400        # FMRI
TIA_SIG_MOUSE       = 0x00000800        # Mouse axis (aperiodic)
TIA_SIG_MOUSE_BTN   = 0x00001000        # Mouse buttons (aperiodic)

TIA_SIG_USER_1      = 0x00010000        # User 1
TIA_SIG_USER_2      = 0x00020000        # User 2 
TIA_SIG_USER_3      = 0x00040000        # User 3
TIA_SIG_USER_4      = 0x00080000        # User 4
TIA_SIG_UNDEFINED   = 0x00100000        # undefined signal type
TIA_SIG_EVENT       = 0x00200000        # event 

# Control message commands
TIA_CTRL_CHECK_PROTO_VERSION            = 'CheckProtocolVersion'
TIA_CTRL_GET_METAINFO                   = 'GetMetaInfo'
TIA_CTRL_GET_DATA_CONNECTION            = 'GetDataConnection'
TIA_CTRL_START_DATA_TRANSMISSION        = 'StartDataTransmission'
TIA_CTRL_STOP_DATA_TRANSMISSION         = 'StopDataTransmission'
TIA_CTRL_GET_SERVER_STATE_CONNECTION    = 'GetServerStateConnection'

# Supported version string (should match real Signal Server!)
TIA_VERSION = '1.0'

# Every control message & response starts with this header
TIA_MSG_HEADER      = 'TiA %s' % TIA_VERSION
# Response to a successful control message
TIA_OK_MSG          = 'TiA %s\nOK\n\n' % TIA_VERSION
# Basic error response
TIA_ERROR_MSG       = 'TiA %s\nError\n\n' % TIA_VERSION
# Extended error response
TIA_ERROR_DESC_MSG  = 'TiA %s\nError\nContent-Length:%d\n\n%s' 

# TiA raw data packet header 
TIA_RAW_HEADER      = struct.Struct('<BIIQQQ')
# TiA raw data packet version magic number
TIA_RAW_VERSION = 0x03

# pass instances of this class to the server to tell it the format of the
# data that will be streamed through it. each class represents one "signal",
# which can contain multiple channels.
class TiASignalConfig(object):
    
    def __init__(self, channels, sample_rate, blocksize, callback, is_master=True, type='user_1', signal_flags=TIA_SIG_USER_1):
        self.channels = channels
        self.sample_rate = sample_rate
        self.blocksize = blocksize
        self.type = type
        self.signal_flags = signal_flags
        self.master = is_master
        assert callback != None, "Must provide a data callback for every signal!"
        self.callback = callback
        # raw data for each signal is a series of floats, with blocksize
        # samples per channel
        self.raw_data = struct.Struct('<' + 'f' * (self.channels * self.blocksize))

    def get_metainfo(self):
        metainfo = ''
        if self.master:
            metainfo += '<masterSignal samplingRate="%d" blockSize="%d"/>\n' % (self.sample_rate, self.blocksize)

        metainfo += '<signal type="%s" samplingRate="%d" blockSize="%d" numChannels="%d">\n' \
                        (self.type, self.sample_rate, self.blocksize, self.channels)
        for i in range(self.channels):
            metainfo += '<channel nr="%d" label="channel%d"/>\n' % (i+1, i+1)
        metainfo += '</signal>\n'
        return metainfo

# just used to handle the basic TCP server functionality required
class TiAServer(ThreadingMixIn, TCPServer): 

    def start(self, signals, single_shot=False, subj_id='subject0', subj_fname='ABC', subj_lname='DEF'):
        assert len(signals) > 0, "Must have at least 1 signal!"
        num_master = 0
        for i, sig in enumerate(signals):
            if sig.master:
                num_master += 1
                self.master_sample_rate = sig.sample_rate
                assert i == 0, "Master signal must be first in the signal list!"
        assert num_master == 1, "Must have exactly one 'Master' signal!"

        self.signals = signals
        self.subject = (subj_id, subj_fname, subj_lname)
        self.start_time = time.time()
        server_target = self.serve_forever

        if single_shot:
            server_target = self.handle_request
            
        t = threading.Thread(target=server_target)    
        t.start()
        print('TiAServer started on %s:%d' % (self.server_address))
        print('TiAServer configured with %d signals' % len(self.signals))
    
# an instance of this class is created each time a client requests
# a data connection. the socket passed in is already bound and listening
# for connections. it waits for an incoming connection from the client,
# then pauses until the server receives a 'StartDataTransmission' command.
# After that it starts streaming data until told to stop. 
class TiATCPClientHandler(threading.Thread):

    def __init__(self, sock, signals, server_start_time, ):
        super(TiATCPClientHandler, self).__init__()
        self.allow_reuse_address = True # equivalent to setting SO_REUSEADDR
        self.sock = sock
        self.finished = False       # indicates end of the client connection
        self.streaming = False      # indicates current state of data streaming
        self.signals = signals
        self.server_start_time = server_start_time

    def run(self):
        try:
            # wait for the TiA client to connect (the server will have sent
            # it the port to use)
            self.conn, remoteaddr = self.sock.accept()
            print('ClientHandler: Data connection from %s:%d' % remoteaddr)
            
            # set up some network stuff that only needs done once
            fmt = 'h' * len(self.signals)
            # variable header struct should be configured to contain 2 arrays of 
            # 16-bit integers (the number of channels in each signal in the first
            # and the blocksize of each signal in the second)
            var_header = struct.Struct('<' + fmt + fmt)
            sig_channels = [x.channels for x in self.signals]
            sig_blocksizes = [x.blocksize for x in self.signals]
            var_header_data = var_header.pack(*(sig_channels + sig_blocksizes))

            # these fields have to be updated in the header for every packet
            packet_id, conn_packet_number, timestamp = 0, 0, 0
            # this indicates what type of data is being streamed (from predefined list above)
            signal_type_flags = 0
            total_raw_data_size = 0
            for s in self.signals:
                signal_type_flags |= s.signal_flags
                total_raw_data_size += s.raw_data.size
                
            # packet size: fixed header + variable header + data
            packet_size = TIA_RAW_HEADER.size + len(var_header_data) + total_raw_data_size

            # now wait until request to start transmission arrives from the client
            while not self.streaming:
                time.sleep(0.01)
                
            print('ClientHandler: Received start command, streaming data...')

            # continue until the StopDataTransmission command is received or 
            # the client disconnects
            while not self.finished:
                # concatenate all the raw signal data together
                raw_data = ''
                for sig in self.signals:
                    sig_data = sig.callback()
                    raw_data += sig.raw_data.pack(*sig_data)
                    
                packet = TIA_RAW_HEADER.pack(TIA_RAW_VERSION, packet_size, 
                            signal_type_flags, packet_id, conn_packet_number,
                            timestamp) + var_header_data + raw_data

                self.conn.send(packet)
                
                # not clear from the spec what the difference is between the 
                # "Packet ID" and "Connection Packet Number" fields, but don't
                # think they're particularly important as long as the values
                # get incremented predictably...
                packet_id += 1
                conn_packet_number += 1
                # this is supposed to be the number of microseconds since the 
                # server started (although it's ignored by the BBT architecture
                # which generates its own timestamps)
                timestamp = long((time.time() - self.server_start_time) * 1000000)

                time.sleep(1.0/self.signals[0].sample_rate)

            self.conn.close()
        except Exception as e:
            print('Error in TCP handler:', e)
            import traceback
            print traceback.format_exc()

        self.sock.close()

# Handler class for the TCPServer instance
class TiAConnectionHandler(BaseRequestHandler):

    def handle(self):
        self.datahandler = None # TODO multiple handlers?

        while True:
            print('>>>>>> BEGIN')
            msg = self.request.recv(256).decode('utf-8')

            msg = filter(bool, msg)
            print('<<<<<< END')

            # control messages are multi-line
            msg = msg.split('\n')

            if len(msg) < 2 or not msg[0].startswith(TIA_MSG_HEADER):
                self.request.sendall(self._get_error_response('Unknown protocol version (requires "%s")' % TIA_VERSION))
                return

            msg_type = msg[1]
            print('Type "%s"\n' % msg_type)

            if msg_type == TIA_CTRL_CHECK_PROTO_VERSION:
                # TODO check the protocol version
                self.request.sendall(TIA_OK_MSG)
            elif msg_type == TIA_CTRL_GET_METAINFO:
                # respond with the signal information that the "server" is configured to provide
                metainfo = '<tiaMetaInfo version="1.0">\n'
                metainfo += '<subject id="%s" firstName="%s" surname="%s"/>\n' % self.server.subject
                for s in self.signals:
                    metainfo += s.get_metainfo()

                metainfo += '</tiaMetaInfo>\n\n'
                # the length value is *only* the actual XML content, the preceding empty newline char shouldn't be included
                resp = TIA_MSG_HEADER + '\nMetaInfo\nContent-Length:' + str(len(metainfo)) + '\n\n' + metainfo
                self.request.sendall(resp.encode('utf-8'))
            elif msg_type.startswith(TIA_CTRL_GET_DATA_CONNECTION):
                # client has requested a data connection, respond with a port number
                # and set up a handler object to deal with the incoming connection
                self.request.sendall(self._get_data_connection_response())
                self.datahandler.start() 
            elif msg_type == TIA_CTRL_START_DATA_TRANSMISSION:
                if self.datahandler == None:
                    self.request.sendall(self._get_data_connection_response('Must send GetDataConnection message first'))
                else:
                    self.request.sendall(TIA_OK_MSG)
                    self.datahandler.streaming = True # begin streaming data
            elif msg_type == TIA_CTRL_STOP_DATA_TRANSMISSION:
                if self.datahandler == None:
                    self.request.sendall(self._get_data_connection_response('No existing data connection!'))
                else:
                    self.request.sendall(TIA_OK_MSG)
                    self.datahandler.finished = True
            else:
                self.request.sendall(self._get_error_response('Unknown message type "%s"' % msg_type))
                return

    def _get_error_response(self, error_msg):
        return TIA_ERROR_DESC_MSG % (TIA_VERSION, len(error_msg), error_msg)

    def _get_signal_info(self):
        pass

    def _get_data_connection_response(self):
        print('Creating a TCP client handler on %s' % (self.server.server_address[0]))
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP)
        # initially bind to port 0 to cause the OS to allocate a free port for us
        sock.bind((self.server.server_address[0], 0))
        # then retrieve the port number that was allocated
        port = sock.getsockname()[1]
        print('Listening on %s:%d' % (sock.getsockname()))
        sock.listen(1)
        self.datahandler = TiATCPClientHandler(sock, self.server.signals, self.server.start_time)
        return TIA_MSG_HEADER + '\nDataConnectionPort:%d\n\n' % port


# this is probably only useful for testing the server class
class TiAClient(object):

    def __init__(self, server_address, server_port):
        self.address = (server_address, server_port)
        self.ctrl_socket = None
        self.data_socket = None
        self.tcp_mode = True # TODO UDP mode too? 
        self.bufsize = 1024
        self.var_header = None
        self.signal_data = []

    def connect(self):
        # create a control connection to the signal server
        self.ctrl_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP)
        try:
            self.ctrl_socket.connect(self.address)
        except socket.error:
            return False

        return True

    def disconnect(self):
        if not self.ctrl_socket:
            return False
        
        try:
            self.ctrl_socket.close()
        except socket.error:
            return False

        return True

    def _send_ctrl_message(self, msg):
        if not self.ctrl_socket:
            return (False, [])

        self.ctrl_socket.send(msg)
        resp = self.ctrl_socket.recv(1024)
        resp = resp.split('\n')
        if not resp[0].startswith(TIA_MSG_HEADER):
            return (False, [])
        return (True, resp)

    def _is_ok_response(self, resp):
        if len(resp) < 2:
            return False
        return resp[1] == "OK"

    def cmd_check_protocol_version(self):
        msg = TIA_MSG_HEADER + '\n' + TIA_CTRL_CHECK_PROTO_VERSION + '\n\n'
        status, resp = self._send_ctrl_message(msg)
        if not status:
            return False

        return self._is_ok_response(resp)

    def cmd_get_metainfo(self):
        msg = TIA_MSG_HEADER + '\n' + TIA_CTRL_GET_METAINFO + '\n\n'
        status, resp = self._send_ctrl_message(msg)
        if not status:
            return False

        # TODO should really parse response + extract signal info here if doing
        # things the right way...

        return self._is_ok_response(resp)

    def cmd_get_data_connection_udp(self):
        return self._cmd_get_data_connection('UDP')

    def cmd_get_data_connection_tcp(self):
        return self._cmd_get_data_connection('TCP')

    def _cmd_get_data_connection(self, proto):
        msg = TIA_MSG_HEADER + '\n' + TIA_CTRL_GET_DATA_CONNECTION + ':' + proto + '\n\n'
        status, resp = self._send_ctrl_message(msg)
        if not status:
            return (False, 0)

        if len(resp) >= 2 and resp[1].startswith('DataConnectionPort'):
            dport = int(resp[1][resp[1].index(':')+1:])
            return (True, dport)

        return (False, 0)

    def _cmd_start_data_transmission(self):
        msg = TIA_MSG_HEADER + '\n' + TIA_CTRL_START_DATA_TRANSMISSION + '\n\n'
        status, resp = self._send_ctrl_message(msg)
        if not status:
            return False

        return self._is_ok_response(resp)

    def _cmd_stop_data_transmission(self):
        msg = TIA_MSG_HEADER + '\n' + TIA_CTRL_STOP_DATA_TRANSMISSION + '\n\n'
        status, resp = self._send_ctrl_message(msg)
        if not status:
            return False

        return self._is_ok_response(resp)

    def cmd_get_server_state_connection(self):
        # TODO (optional thing)
        pass

    def start_streaming_data_tcp(self, server_address, data_port):
        return self._start_streaming_data(server_address, data_port, 'TCP')

    def start_streaming_data_udp(self, server_address, data_port):
        # TODO
        pass

    def _start_streaming_data(self, server_address, data_port, proto):
        assert (proto == 'UDP') or (proto == 'TCP')

        # do this first to set up things on the server side
        if not self._cmd_start_data_transmission():
            return False

        if proto == 'UDP':
            self.data_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            self.tcp_mode = False
            
        else:
            self.data_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP)
            self.data_socket.connect((server_address, data_port))
            self.tcp_mode = True

            return True
    
    def stop_streaming_data(self):
        if not self._cmd_stop_data_transmission():
            return False

        self.data_socket.close()

        return True

    def get_data(self):
        if not self.tcp_mode:
            return None # TODO UDP mode
        
        data = self.data_socket.recv(self.bufsize)
        # strip off header info and unpack data
        fixed_header = TIA_RAW_HEADER.unpack(data[:TIA_RAW_HEADER.size])
        if fixed_header[0] != 3 or fixed_header[1] != len(data):
            return []

        # count up number of flags set in the signal_type_flags field of the header
        # (should be one bit set for each distinct signal)
        num_signals = bin(fixed_header[2]).count('1')
        print('Number of signals: %d' % num_signals)

        # once we know that, we can parse the variable header to get the number
        # of channels and blocksize of each signal...
        if self.var_header == None:
            self.var_header = struct.Struct('<' + ('h' * num_signals * 2))

        var_header_data = self.var_header.unpack(data[TIA_RAW_HEADER.size:TIA_RAW_HEADER.size+self.var_header.size])

        # now retrieve the samples from each signal. when blocksize > 1, the
        # samples are ordered like this (blocksize=4):
        # ch1s1, ch1s2, ch1s3, ch1s4, ch2s1, ch2s2, ...
        alldata = []
        if len(self.signal_data) == 0:
            for i in range(num_signals):
                channels = var_header_data[i]
                blocksize = var_header_data[num_signals+i]
                self.signal_data.append(struct.Struct('<' + ('f' * channels * blocksize)))
        else:
            index = TIA_RAW_HEADER.size + self.var_header.size
            for s in self.signal_data:
                alldata.append(s.unpack(data[index:index+s.size]))
                index += s.size

        return alldata


def sk7_imu_callback():
    return [random.randint(-1000, 1000) for x in range(5)]

if __name__ == "__main__":
    server = TiAServer(('127.0.0.1', 9000), TiAConnectionHandler)
    server.start([TiASignalConfig(5, 100, 1, sk7_imu_callback, True), TiASignalConfig(5, 100, 1, sk7_imu_callback, False, type='user_2', signal_flags=TIA_SIG_USER_2)])
    print('Waiting for requests')

