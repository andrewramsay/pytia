from socket import *
import sys, time, random
import pytia

# Simple demo of TiA client/server comms process

def data_callback(signalid):
    return [random.uniform(-1000, 1000) for x in range(3)]

if __name__ == "__main__":
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
                packet = packets[0]
                print('Dumping first packet info...')
                print('Packet metadata: ', packet.timestamp, packet.packet_id, packet.packet_number)
                print('%d signals in packet' % (len(packet.signals)))
                print('Channel counts: ', packet.channels)
                print('Block sizes: ', packet.blocksizes)
                # accessing data selectively by channel
                for i in range(packet.channels[0]):
                    print('1st signal data [channel %d/%d]' % (i, packet.channels[0])),
                    print(packet.get_channel(0, i))
                # accessing all signal data in one go
                print('1st signal data [all]'),
                print(packet.get_channel(0))
                #for i in range(packet.channels[0]):
                #    print('   Channel %d:' % i, packet.get_channel(0, i))
            time.sleep(0.05)
        except KeyboardInterrupt:
            done = True

    # the client should tell the server to stop streaming before 
    # disconnecting itself
    client.stop_streaming_data()
    client.disconnect()

