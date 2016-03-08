# -*- coding: utf-8 -*-
import struct, socket, threading, time, random, sys

if sys.version_info > (3,):
    from socketserver import BaseRequestHandler, ThreadingMixIn, TCPServer
    long = int
else:
    from SocketServer import BaseRequestHandler, ThreadingMixIn, TCPServer

TIA_ENCODING = 'utf-8'

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

TIA_SIG_NAMES = { \
        TIA_SIG_EEG:        'eeg',
        TIA_SIG_EMG:        'emg',
        TIA_SIG_EOG:        'eog',
        TIA_SIG_ECG:        'ecg',
        TIA_SIG_HR:         'hr',
        TIA_SIG_BP:         'bp',
        TIA_SIG_BUTTON:     'button',
        TIA_SIG_JOYSTICK:   'joystick',
        TIA_SIG_SENSORS:    'sensors',
        TIA_SIG_NIRS:       'nirs',
        TIA_SIG_FMRI:       'fmri',
        TIA_SIG_MOUSE:      'mouse',
        TIA_SIG_MOUSE_BTN:  'mouse-button',
        TIA_SIG_USER_1:     'user_1',
        TIA_SIG_USER_2:     'user_2',
        TIA_SIG_USER_3:     'user_3',
        TIA_SIG_USER_4:     'user_4',
        TIA_SIG_UNDEFINED:  'undefined',
        TIA_SIG_EVENT:      'event',
}

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
TIA_OK_MSG          = ('TiA %s\nOK\n\n' % TIA_VERSION).encode(TIA_ENCODING)
# Basic error response
TIA_ERROR_MSG       = ('TiA %s\nError\n\n' % TIA_VERSION).encode(TIA_ENCODING)
# Extended error response
TIA_ERROR_DESC_MSG  = 'TiA %s\nError\nContent-Length:%d\n\n%s' 

# TiA raw data packet header 
TIA_RAW_HEADER      = struct.Struct('<BIIQQQ')
# TiA raw data packet version magic number
TIA_RAW_VERSION = 0x03

class TiAException(Exception): 
    pass

class TiASignalConfig(object):
    """
    Encapsulates information about a single signal to be streamed through
    a TiAServer instance, including number of channels, sample rate, blocksize 
    (the number of samples per channel in each outgoing packet) and data type.
    """

    def __init__(self, channels, sample_rate, blocksize, callback, id, is_master=True, type=TIA_SIG_USER_1):
        """ 
        Create a signal. Parameters are:
            
            channels:       the number of channels in the signal (eg for an accelerometer with 
                            3 axes you would have 3 channels).

            sample_rate:    rate in Hz that the server should poll the provider of this signal
                            for new data. Note that this value is actually ignored for any
                            signals other than the 'master' signal! (see 'is_master' 
                            parameter).

            blocksize:      sets the number of samples the server will expect to be provided
                            with every time it polls the signal callback method. For example,
                            if you have 3 channels and a blocksize of 2, it will expect to
                            receive 2 samples for each channel for a total of 6 values.

            callback:       a method that when called by the server will return a flat list of
                            blocksize samples per channel. For example, with 2 channels and
                            a blocksize of 2, this method should return a list containing
                            [ch1s1, ch2s2, ch2s1, ch2s2].

            id:             arbitrary object/value that can be used to identify the signal
                            and/or associate data with it. Whatever is provided here will
                            be passed as a parameter to the callback method. 

            is_master:      indicates if this signal is the 'master' signal. The 'master' 
                            signal sampling rate is the rate at which the server will 
                            poll the set of signal callback methods for new data. Exactly
                            one signal must be set as the master signal within each instance
                            of a TiAServer.

            type:           sets the TiA type of the signal. This should be one of the 
                            TIA_SIG_NAME_USER_ constants. If you have multiple signals,
                            you must use a different type for every signal. The default
                            value is fine for a single signal. 

        """
        self.channels = channels
        self.sample_rate = sample_rate
        self.blocksize = blocksize
        self.id = id
        self.signal_flags = type
        self.typestr = TIA_SIG_NAMES[type]
        self.master = is_master
        if callback == None:
            raise TiAException("Must provide a valid callback method for every signal")
        
        self.callback = callback
        # raw data for each signal is a series of floats, with blocksize
        # samples per channel
        self.raw_data = struct.Struct('<' + 'f' * (self.channels * self.blocksize))

    def get_metainfo(self):
        """
        This method generates the XML signal description that the TiA server 
        provides to TiA clients so that they can parse the data they receive. It
        is only called by the TiAServer instance containing this signal config. 
        """
        metainfo = ''
        if self.master:
            metainfo += '<masterSignal samplingRate="%d" blockSize="%d"/>\n' % (self.sample_rate, self.blocksize)

        metainfo += '<signal type="%s" samplingRate="%d" blockSize="%d" numChannels="%d">\n' \
                    % (self.typestr, self.sample_rate, self.blocksize, self.channels)
        for i in range(self.channels):
            metainfo += '<channel nr="%d" label="channel%d"/>\n' % (i+1, i+1)
        metainfo += '</signal>\n'
        return metainfo

class TiAServer(ThreadingMixIn, TCPServer): 
    """
    SocketServer-based TCP server with threading support via the MixIn class.
    
    This class implements the actual TCP server functionality, but the bulk of the
    TiA code is in the TiATCPClientHandler class.
    """
    
    def start(self, signals, single_shot=False, subj_id='subject0', subj_fname='ABC', subj_lname='DEF'):
        """
        Call this function after creating the server object to begin listening for
        connections from TiA clients. 

        Parameters:

            signals:        a list of one or more TiASignalConfig objects, exactly
                            one of which must be configured as the 'master' signal.

            single_shot:    if True, the server will only handle a single request and 
                            then shut down. The default is to continue indefinitely.

            subj_id:        subject ID (this is ignored by BBT architecture)

            subj_fname:     subject first name (this is ignored by BBT architecture)

            subj_lname:     subject surname (this is ignored by BBT architecture)
        """

        if len(signals) < 1:
            raise TiAException("Must have at least 1 signal!")

        num_master, master_index = 0, 0
        for i, sig in enumerate(signals):
            if sig.master:
                num_master += 1
                master_index = i
                self.master_sample_rate = sig.sample_rate
        
        if num_master != 1:
            raise TiAException('Must have exactly one "Master" signal (found %d)' % num_master)

        # put the master signal first in the list if it isn't there already
        if not signals[0].master:
            signals.insert(0, signals.pop(master_index))

        self.signals = signals
        self.subject = (subj_id, subj_fname, subj_lname)
        self.start_time = time.time()
        server_target = self.serve_forever

        if single_shot:
            server_target = self.handle_request
            
        t = threading.Thread(target=server_target)    
        t.daemon = True
        t.start()
        print('TiAServer started on %s:%d' % (self.server_address))
        print('TiAServer configured with %d signals' % len(self.signals))
    
# an instance of this class is created each time a client requests
# a data connection. the socket passed in is already bound and listening
# for connections. it waits for an incoming connection from the client,
# then pauses until the server receives a 'StartDataTransmission' command.
# After that it starts streaming data until told to stop. 
class TiATCPClientHandler(threading.Thread):
    """
    Instances of this class are created each time a client requests a data 
    connection from the server. Each encapsulates a thread that polls the 
    sensor callbacks defined by the signal data, and sends TiA packets to the
    connected client. 

    TODO: should really only poll the sensors in one place, not in every
    instance of this class (only a problem if multiple clients)
    """

    def __init__(self, sock, signals, server_start_time):
        """
        Parameters:
            
            sock:       the TCP socket created by the server in response to the
                        client request. The socket is passed in in the pre-accept()
                        state, ready to await the incoming connection once the 
                        accept() method is called. 

            server_start_time:      timestamp giving server start time. Used to 
                                    generate timestamps for outgoing packets, although
                                    the BBT architecture discards these.
        """
        super(TiATCPClientHandler, self).__init__()
        self.allow_reuse_address = True # equivalent to setting SO_REUSEADDR
        self.sock = sock
        self.finished = False       # indicates end of the client connection
        self.streaming = False      # indicates current state of data streaming
        self.signals = signals
        self.server_start_time = server_start_time

    def run(self):
        """
        Starts the thread to receive the incoming connection from the client, 
        and then to begin streaming data back to it until told to stop.
        """
        try:
            # wait for the TiA client to connect (the server will have sent
            # it the port to use)
            self.conn, remoteaddr = self.sock.accept()
            print('TiATCPClientHandler: Data connection from %s:%d' % remoteaddr)
            
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
                
            print('TiATCPClientHandler: Received start command, streaming data...')

            # continue until the StopDataTransmission command is received or 
            # the client disconnects
            while not self.finished:
                # concatenate all the raw signal data together
                raw_data = b''
                for sig in self.signals:
                    sig_data = sig.callback(sig.id)
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
            print(traceback.format_exc())

        self.sock.close()

# Handler class for the TCPServer instance
class TiAConnectionHandler(BaseRequestHandler):

    def handle(self):
        self.datahandler = None # TODO multiple handlers?

        while True:
            msg = self.request.recv(4096).decode(TIA_ENCODING)

            # control messages are multi-line
            msg = msg.split('\n')
            msg = list(filter(bool, msg))

            if len(msg) < 2 or not msg[0].startswith(TIA_MSG_HEADER):
                self.request.sendall(self._get_error_response('Unknown protocol version (requires "%s")' % TIA_VERSION))
                return

            msg_type = msg[1]

            if msg_type == TIA_CTRL_CHECK_PROTO_VERSION:
                # TODO check the protocol version
                self.request.sendall(TIA_OK_MSG)
            elif msg_type == TIA_CTRL_GET_METAINFO:
                # respond with the signal information that the "server" is configured to provide
                metainfo = '<tiaMetaInfo version="1.0">\n'
                metainfo += '<subject id="%s" firstName="%s" surname="%s"/>\n' % self.server.subject
                for s in self.server.signals:
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
                    self.request.sendall(self._get_error_response('Must send GetDataConnection message first'))
                else:
                    self.request.sendall(TIA_OK_MSG)
                    self.datahandler.streaming = True # begin streaming data
            elif msg_type == TIA_CTRL_STOP_DATA_TRANSMISSION:
                if self.datahandler == None:
                    self.request.sendall(self._get_error_response('No existing data connection!'))
                else:
                    self.request.sendall(TIA_OK_MSG)
                    self.datahandler.finished = True
            else:
                self.request.sendall(self._get_error_response('Unknown message type "%s"' % msg_type))
                return

    def _get_error_response(self, error_msg):
        resp = TIA_ERROR_DESC_MSG % (TIA_VERSION, len(error_msg), error_msg)
        return resp.encode(TIA_ENCODING)

    def _get_signal_info(self):
        pass

    def _get_data_connection_response(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP)
        # initially bind to port 0 to cause the OS to allocate a free port for us
        sock.bind((self.server.server_address[0], 0))
        # then retrieve the port number that was allocated
        port = sock.getsockname()[1]
        sock.listen(1)
        self.datahandler = TiATCPClientHandler(sock, self.server.signals, self.server.start_time)
        resp = TIA_MSG_HEADER + '\nDataConnectionPort:%d\n\n' % port
        return resp.encode(TIA_ENCODING)


# this is probably only useful for testing the server class
class TiAClient(object):

    def __init__(self, server_address, server_port):
        self.address = (server_address, server_port)
        self.ctrl_socket = None
        self.data_socket = None
        self.bufsize = 1024
        self.var_header = None
        self.signal_data = []
        self.last_buffer = b''

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

        self.ctrl_socket.send(msg.encode(TIA_ENCODING))
        # TODO this shouldn't be a fixed buffer size as the message can be
        # quite big in the case of the GetMetaInfo command with multiple signals
        resp = self.ctrl_socket.recv(4096).decode(TIA_ENCODING)
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

    def _start_streaming_data(self, server_address, data_port, proto):
        if proto != 'TCP':
            raise TiAException('Protocol "%s" not supported' % proto)

        # do this first to set up things on the server side
        if not self._cmd_start_data_transmission():
            return False

        self.data_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP)
        self.data_socket.connect((server_address, data_port))

        return True
    
    def stop_streaming_data(self):
        if not self._cmd_stop_data_transmission():
            return False

        self.data_socket.close()

        return True

    def get_data(self):
        data = self.data_socket.recv(self.bufsize)

        if len(self.last_buffer) > 0:
            data = self.last_buffer + data
            self.last_buffer = b''

        # might have multiple packets in the buffer here. this doesn't
        # handle packets that straddle a buffer boundary, just multiple
        # complete packets in the same buffer
        offset = 0
        packets = []
        while (offset + TIA_RAW_HEADER.size) < len(data):
            # strip off header info and unpack data
            fixed_header = TIA_RAW_HEADER.unpack(data[offset:offset+TIA_RAW_HEADER.size])
            if fixed_header[0] != TIA_RAW_VERSION or fixed_header[1] > len(data)-offset:
                # invalid packet/packet too small
                # TODO in case there's actually a valid header, could just read
                # the rest of the packet here since we will know the size
                print('TiAClient: WARNING, invalid packet %d==%d, %d > %d' % (fixed_header[0], TIA_RAW_VERSION, fixed_header[1], len(data)-offset))
                return packets

            packet = data[offset:offset+fixed_header[1]]
            packets.append(self._process_packet(packet, fixed_header))
            offset += fixed_header[1]

        self.last_buffer = data[offset:]
        return packets

    def _process_packet(self, packet, header):
        # count up number of flags set in the signal_type_flags field of the header
        # (should be one bit set for each distinct signal)
        num_signals = bin(header[2]).count('1')

        # once we know that, we can parse the variable header to get the number
        # of channels and blocksize of each signal...
        if self.var_header == None:
            self.var_header = struct.Struct('<' + ('h' * num_signals * 2))

        var_header_data = self.var_header.unpack(packet[TIA_RAW_HEADER.size:TIA_RAW_HEADER.size+self.var_header.size])

        # now retrieve the samples from each signal. when blocksize > 1, the
        # samples are ordered like this (blocksize=4):
        # ch1s1, ch1s2, ch1s3, ch1s4, ch2s1, ch2s2, ...
        alldata = []
        if len(self.signal_data) == 0:
            for i in range(num_signals):
                channels = var_header_data[i]
                blocksize = var_header_data[num_signals+i]
                self.signal_data.append(struct.Struct('<' + ('f' * channels * blocksize)))

        index = TIA_RAW_HEADER.size + self.var_header.size
        for s in self.signal_data:
            alldata.append(s.unpack(packet[index:index+s.size]))
            index += s.size

        return alldata


def sk7_imu_callback(id):
    return [random.uniform(-1000, 1000) for x in range(3)]

if __name__ == "__main__":
    server = TiAServer(('', 9000), TiAConnectionHandler)
    # example setup for SK7 IMUs
    server.start([TiASignalConfig(3, 100, 1, sk7_imu_callback, i, i == 0, 2 ** (i+16)) for i in range(5)])
    print('Waiting for requests')

    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        pass

    print ('Exiting')

