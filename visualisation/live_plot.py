import dash
import plotly
import plotly.express as px
import pandas as pd
import random
import numpy as np
import pylsl
import plotly.graph_objs as go
from dash.dependencies import Output, Input
from dash import html
from dash import dcc
from waitress import serve
from visualisation.utils.logging import logger
from mne_lsl.stream import StreamLSL,EpochsStream
from mne_lsl.lsl import StreamInlet,StreamInfo,resolve_streams

"""Script to initialize a Dash server on which to show Plotly plot"""

streams = resolve_streams(name='output_average_stream')
TIME = np.arange(-200,500,10) 
x = px.line()
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

if len(streams) > 0:
    data_stream = StreamInlet(streams[0])

else:
    data_stream = None

if data_stream != None:
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
    
    buf_data = data_stream.pull_sample()
    N = buf_data[0][0] #number of epochs used for average
    EEG_average = buf_data[0][1:].reshape(1,70) 
    print((EEG_average.shape))
    data = plotly.graph_objs.Scatter(
            x=TIME,
            y=list(EEG_average[0,:70]),
            name='Scatter',
            mode= 'lines'
    )

    title = f"Number of epochs {int(N)}"
    return {'data': [data],
                'layout' : go.Layout(xaxis=dict(range=[TIME[0],TIME[-1]]),yaxis = dict(range = [min(EEG_average[0,:70]),max(EEG_average[0,:70])]),title=title)}

def run_plot(host='127.0.0.1',port=8088):
    """start the server and show the plot
    params:
    host: str 
        address for the dash server (default localhost)
    port: int
        output port for the dash server
    """
    serve(app,host=host,port=port)

if __name__ == "__main__":
    serve(app, host='127.0.0.1', port=8088)
