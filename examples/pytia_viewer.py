from socket import *
import sys, time, random, math
import pytia
import Tkinter as tk
# Simple demo of TiA client/server comms process

class Viewer(object):
    def __init__(self):
        # create root window widget
        self.root = tk.Tk()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # create label for displaying status information
        self.status_label = tk.Label(self.root, text="Viewer waiting for packets!")
        self.status_label.pack()
        
        # is true if window delete event has been fired; returned by update.
        self.is_alive = True
        self.signal_streams = []
        # render window
        self.update()
        
    def update(self, packets=None):
        if self.is_alive:
            # code for displaying data from new packets goes here
            if packets is not None:
                for packet in packets:
                    self.process_packet(packet)
                self.update_charts()
                self.status_label.config(text='Number of values in channel 0 for signal 0: ' + str(len(self.signal_streams[0][0])))
            else:
                self.status_label.config(text='No new packet received.')
            # tkinter event handlers
            self.root.update_idletasks()
            self.root.update()
        return self.is_alive
        
    def process_packet(self, packet):
        # initialise list of signals on first call
        if self.signal_streams == []:
            for s in range(len(packet.signals)):
                # initialise empty channel list for each signal
                self.signal_streams.append([])
                for c in range(packet.channels[s]):
                    # initialise empty data list for each channel
                    self.signal_streams[s].append([])
        # append packet data to correct signal channel
        for s in range(len(packet.signals)):
            for c in range(packet.channels[s]):
                self.signal_streams[s][c] += list(packet.get_channel(s, c))
        
    def update_charts(self):
        # initialise charts after first packets have been received
        if self.signal_streams is not []:
            # has some data
            if not hasattr(self, 'charts'):
                # initialise one canvas per signal channel
                self.charts = []
                for s in range(len(self.signal_streams)):
                    self.charts.append([])
                    frame = tk.LabelFrame(self.root, text="Signal {}:".format(s))
                    frame.pack()
                    for c in range(len(self.signal_streams[s])):
                        chart = tk.Canvas(frame, width=800, height=100, bg='white')
                        self.charts[s].append(chart)
                        chart.pack()
        # update/ draw chart
        for s in range(len(self.signal_streams)):
            for c in range(len(self.signal_streams[s])):
                self.draw(self.charts[s][c], self.signal_streams[s][c])
                
    def draw(self, chart, channel_data):
        chart.delete('all')
        # margins
        margin_left = 30
        margin_bottom = 15
        margin_top = 10
        # x,y data to coordinate mapping
        num_samples = len(channel_data)
        step = (chart.winfo_width()-margin_left)/float(num_samples)
        channel_min = min(0, min(channel_data))
        channel_max = max(channel_data)
        channel_range = channel_max - channel_min
        scale = channel_range/(chart.winfo_height()-margin_bottom-margin_top) + 1e-7
        def coords(i, value):
            x = i*step + margin_left
            y = chart.winfo_height()-margin_bottom - (value - channel_min)/scale
            return x, y

        # chrome
        #   y-axis
        grid_y = 4
        for i in range(grid_y+1):
            value = channel_min + i*channel_range/grid_y
            x_axis_x , x_axis_y = coords(0, value)
            chart.create_text(2, x_axis_y, text="{:2.2f}".format(value), anchor=tk.W)
            chart.create_line(x_axis_x, x_axis_y, chart.winfo_width(), x_axis_y, fill="#cccccc")
        base = 5
        label_scale = int(math.log(num_samples)/math.log(base))-1
        grid_x = 1+int(num_samples/base**label_scale)
        for i in range(grid_x+1):
            value = i*base**label_scale
            y_axis_x, y_axis_y = coords(value, channel_min)
            chart.create_text(y_axis_x, y_axis_y+7, text="{:2.0f}".format(value))
            chart.create_line(y_axis_x, y_axis_y, y_axis_x, margin_top, fill="#cccccc")
        
        # data plot
        prev_x, prev_y = coords(0,0)
        for i in range(len(channel_data)):
            d_x, d_y = coords(i, channel_data[i])
            chart.create_line(prev_x, prev_y, d_x, d_y, fill="#000000")
            prev_x, prev_y = d_x, d_y
        
    def on_closing(self):
        self.root.destroy()
        self.is_alive = False

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
        
    # the GUI gets initialised
    viewer = Viewer()

    # once connected, the server continues streaming data until told to stop
    done = False
    while not done:
        try:
            # calling the get_data function returns the most recent data received
            # from the server. depending on the buffer size used (TODO?) there may
            # be multiple TiA packets returned here.
            done = not viewer.update(client.get_data())
        except KeyboardInterrupt:
            done = True

    # the client should tell the server to stop streaming before 
    # disconnecting itself
    client.stop_streaming_data()
    client.disconnect()

