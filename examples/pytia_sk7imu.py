import time, sys, itertools

from pyshake import *
import pytia
from pytia import TiAServer, TiAConnectionHandler, TiASignalConfig

# Runs a TiA server configured to stream data from an SK7 with 5 
# wired IMUs attached

def tia_callback(data):
    (sig_id, sig_data) = data
    sk7_dev = sig_data[0]

    # each time the server polls for new data, get the latest sensor readings
    # from each individual IMU, construct a list of their accelerometer,
    # magnetometer and gyroscope values and pass that back to the server
    imudata = sk7_dev.sk7_imus()
    vals = [val for imu in imudata for val in [imu.acc, imu.mag, imu.gyro]]
    return itertools.chain(*vals)

if __name__ == "__main__":
    # connect to the IMUs through the SK7
    sk7_dev  = ShakeDevice(SHAKE_SK7)
    if len(sys.argv) != 2:
        print('Usage: pytia_sk7imu.py <port number>')
        sys.exit(0)

    address = sys.argv[1]

    print('Connecting to SK7 on port %s...' % address)
    if not sk7_dev.connect(address):
        print('Failed to connect')
        sys.exit(-1)

    print('Connected OK!')

    # create a TiAServer on localhost:9000
    server = TiAServer(('', 9000), TiAConnectionHandler)

    # define a single signal for the server to stream to clients. There are 5
    # IMUs and each will be providing 9 channels of data (x/y/z accelerometer,
    # magnetometer and gyroscope), so that's 45 in total. The server will poll
    # for new data at 100Hz, packets will be sent in blocks of 1 and the callback
    # defined above will be used as the data source.
    signal = TiASignalConfig(channels=45, sample_rate=100, blocksize=1, \
                            callback=tia_callback, id=(0, (sk7_dev,)), 
                            is_master=True, sigtype=pytia.TIA_SIG_USER_1)

    # start the server with the list of signals to use
    server.start([signal,])

    print('[Ctrl-C to exit]')
    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print('Closing connection...')

    sk7_dev.close()
