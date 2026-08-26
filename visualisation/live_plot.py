import dash
import plotly
import random
import numpy as np
import pylsl
import plotly.graph_objs as go
from dash.dependencies import Output, Input
from dash import html
from dash import dcc
from waitress import serve
from visualisation.utils.logging import logger
from mne_lsl.stream import StreamLSL
from mne_lsl.lsl import StreamInlet,StreamInfo,resolve_streams

"""Script to initialize a Dash server on which to show Plotly plot"""
print(2)
streams = resolve_streams(name='output_average_stream')
print(streams)
app = dash.Dash(__name__)
app.layout = html.Div(
    [
        dcc.Graph(id = 'live-graph', animate = False),
        dcc.Interval(
            id = 'graph-update',
            interval = 1000,
            n_intervals = 0
        ),
    ]
)

#connect to data stream from Visualisation
# info = StreamInfo(
#                     name='output_average_stream',
#                     type="data",
#                     channel_count=5,
#                     nominal_srate=pylsl.IRREGULAR_RATE,
#                     channel_format=pylsl.cf_float32,
#                     source_id="output_average_stream",
#                 )
data_stream = StreamInlet(streams[0])
# data_stream = StreamLSL(bufsize=4, name="output_average_stream",stype='data', source_id="output_average_stream")
# data_stream.connect(acquisition_delay=0.1, processing_flags="all")
data_stream.open_stream()
@app.callback(
    Output('live-graph', 'figure'),
    [ Input('graph-update', 'n_intervals') ]
)
def update_graph(n):
    """
    Function to update the graph with new data from the LSL stream, 
    this function is automatically called by the dash server
    """
    buf_data = data_stream.pull_chunk()
    new_evoked = buf_data[0][0]
    print(buf_data)
    x = np.random.random((5,))
    x= list(x)
    data = plotly.graph_objs.Scatter(
            x=list(new_evoked),
            y=list(new_evoked),
            name='Scatter',
            mode= 'lines'
    )
    return {'data': [data],
            'layout' : go.Layout(xaxis=dict(range=[-2,4]),yaxis = dict(range = [min(new_evoked),max(new_evoked)]),)}

def run_plot(host='127.0.0.1',port=8088):
    """start the server and show the plot
    params:
    host: str 
        address for the dash server (default localhost)
    port: int
        output port for the dash server
    """
    serve(app,host=host,port=port)

def run_test():
    for i in range(100):
        # print(data_stream.get_data()[1])
        pass

if __name__ == "__main__":
    # run_test()
    print(1)
    serve(app, host='127.0.0.1', port=8088)
