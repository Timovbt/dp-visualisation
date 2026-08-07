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

app = dash.Dash(__name__)
app.layout = html.Div(
    [
        dcc.Graph(id = 'live-graph', animate = True),
        dcc.Interval(
            id = 'graph-update',
            interval = 1000,
            n_intervals = 0
        ),
    ]
)

stream = StreamLSL(bufsize=4, name="output_average_stream",stype='data', source_id="output_average_stream")
stream.connect(acquisition_delay=0.1, processing_flags="all")


@app.callback(
    Output('live-graph', 'figure'),
    [ Input('graph-update', 'n_intervals') ]
)

def update_graph(n):
    print(n)
    buf_data = stream.get_data()
    print(buf_data[1])
    print(buf_data[1].shape)
    new_evoked = buf_data[1]
    # new_evoked = EvokedArray(
    #     [buf_data[1].mean(axis=0)], stream.info, nave=buf_data[1].shape[0]
    #     )
    data = plotly.graph_objs.Scatter(
            x=list(new_evoked),
            y=list(new_evoked),
            name='Scatter',
            mode= 'lines+markers'
    )

    return {'data': [data],
            'layout' : go.Layout(xaxis=dict(range=[min(new_evoked),max(new_evoked)]),yaxis = dict(range = [min(new_evoked),max(new_evoked)]),)}

def run_plot(address,port):
    serve(app,host=address,port=port)

if __name__ == "__main__":
    print('s')
    serve(app, host="0.0.0.0", port=8080)
