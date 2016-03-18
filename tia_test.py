from socket import *
import sys, time, random
import pytia

# Simple demo of TiA client/server comms process

def data_callback(signalid):
    return [random.uniform(-1000, 1000) for x in range(3)]

if __name__ == "__main__":
    # create a server listening on port 9000 and configured with a 3 channel,
    # 100Hz signal (containing random data)
    #server = pytia.TiAServer(('', 9000), pytia.TiAConnectionHandler)
    #server.start([pytia.TiASignalConfig(3, 100, 1, data_callback, 'signalid', pytia.TIA_SIG_USER_1)])

    # (server is now running in a background thread)

    # create a client and connect to the server
    client = pytia.TiAClient('127.0.0.1', 9000)
    if not client.connect():
        print('Failed to connect to server')
        sys.exit(-1)

    # TiA clients must start by checking server protocol version against theirs
    if not client.cmd_check_protocol_version():
        print('Protocol version check failed!')
        client.disconnect()
        sys.exit(-1)

    # The client should now technically use the 'get metainfo' command to 
    # retrieve the signal information the server  has been configured with.
    # TODO this doesn't actually return the actual metainfo data yet
    metainfo = client.cmd_get_metainfo()

    # next, clients should request a TCP data connection (UDP not supported)
    # the server will respond with a port number that the client should connect
    # to in order to start streaming data.
    status, dport = client.cmd_get_data_connection_tcp()
    print(status, dport)
    if not status:
        print('Failed to get data connection')
        client.disconnect()
        sys.exit(-1)

    # the client connects and requests that the server begin streaming data
    print('Connecting to server on port %d...' % dport)
    if not client.start_streaming_data_tcp('127.0.0.1', dport):
        print('Failed to start streaming data')
        client.disconnect()
        sys.exit(-1)

    # once connected, the server continues streaming data until told to stop
    done = False
    while not done:
        try:
            # calling the get_data function returns the most recent data received
            # from the server. depending on the buffer size used (TODO?) there may
            # be multiple TiA packets returned here.
            packets = client.get_data()
            print('----------')
            print('Retrieved %d packets' % (len(packets)))
            if len(packets) > 0:
                print('Dumping first packet info...')
                print('%d signals in packet' % (len(packets[0].signals)))
                print('Channel counts: ', packets[0].channels)
                print('Block sizes: ', packets[0].blocksizes)
                print('1st signal data [%d channels]' % packets[0].channels[0])
                for i in range(packets[0].channels[0]):
                    print('   Channel %d:' % i, packets[0].get_channel(0, i))
            time.sleep(0.1)
        except KeyboardInterrupt:
            done = True

    # the client should tell the server to stop streaming before 
    # disconnecting itself
    client.stop_streaming_data()
    client.disconnect()

