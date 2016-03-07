from socket import *
import sys, time, random
import pytia

# Simple demo of TiA client/server comms process

def data_callback(signalid):
    return [random.uniform(-1000, 1000) for x in range(3)]

if __name__ == "__main__":
    # create a server listening on port 9000 and configured with a 3 channel,
    # 100Hz signal (containing random data)
    server = pytia.TiAServer(('', 9000), pytia.TiAConnectionHandler)
    server.start([pytia.TiASignalConfig(3, 100, 1, data_callback, 'signalid', pytia.TIA_SIG_USER_1)])

    # (server is now running in a background thread)

    # create a client and connect to the server
    client = pytia.TiAClient('localhost', 9000)
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
    if not status:
        print('Failed to get data connection')
        client.disconnect()
        sys.exit(-1)

    # the client connects and requests that the server begin streaming data
    if not client.start_streaming_data_tcp('localhost', dport):
        print('Failed to start streaming data')
        client.disconnect()
        sys.exit(-1)

    # once connected, the server continues streaming data until told to stop
    for i in range(10):
        # calling the get_data function returns the most recent data received
        # from the server. depending on the buffer size used (TODO?) there may
        # be multiple TiA packets returned here.
        packets = client.get_data()
        print('----------')
        print('Retrieved %d packets' % (len(packets)))
        if len(packets) > 0:
            print('%d signals in packet' % (len(packets[0])))

            for i in range(len(packets[0])):
                print('Signal %d:' % (i+1), packets[0][i])

    # the client should tell the server to stop streaming before 
    # disconnecting itself
    client.stop_streaming_data()
    client.disconnect()

