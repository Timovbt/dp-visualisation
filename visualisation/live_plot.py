import dash
import plotly
import random
import numpy as np
import plotly.graph_objs as go
from collections import deque
from mne import EvokedArray
from dash.dependencies import Output, Input
from dash import html
from dash import dcc
from waitress import serve
from visualisation.utils.logging import logger
from mne_lsl.stream import EpochsStream, StreamLSL

"""Script to initialize a Dash server on which to show Plotly plot"""

app = dash.Dash(__name__)
app.layout = html.Div(
    [
        dcc.Graph(id = 'live-plot', animate = True),
        dcc.Interval(
            id = 'plot-update',
            interval = 1000,
            n_intervals = 0
        ),
    ]
)

#connect to data stream from Visualisation
data_stream = StreamLSL(bufsize=4, name="output_average_stream",stype='data', source_id="output_average_stream")
data_stream.connect(acquisition_delay=0.1, processing_flags="all")


@app.callback(
    Output('live-graph', 'figure'),
    [ Input('graph-update', 'n_intervals') ]
)

def update_graph(n):
    """
    Function to update the graph with new data from the LSL stream, 
    this function is automatically called by the dash server
    """
    buf_data = data_stream.get_data()
    print(buf_data[1])
    print(buf_data[1].shape)
    new_evoked = buf_data[1]

    data = plotly.graph_objs.Scatter(
            x=list(new_evoked),
            y=list(new_evoked),
            name='Scatter',
            mode= 'lines+markers'
    )

    return {'data': [data],
            'layout' : go.Layout(xaxis=dict(range=[min(new_evoked),max(new_evoked)]),yaxis = dict(range = [min(new_evoked),max(new_evoked)]),)}

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
