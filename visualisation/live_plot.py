import dash
from dash.dependencies import Output, Input
import dash_core_components as dcc
import dash_html_components as html
import plotly
import random
import plotly.graph_objs as go
from collections import deque

class Live_plot():
    """
    Object to create a dash server to show a live figure from plotly that can be updated with new incoming data.

    Parameters
    ----------

    Attributes
    ----------


    """
    def __init__(self,
                 logger,
                 port,
                 adress,
                 window):
        self.logger = logger
        self.window = window
        pass

        self.X = deque(maxlen = 20)
        self.X.append(1)

        self.Y = deque(maxlen = 20)
        self.Y.append(1)

        self.app = dash.Dash(__name__)

        #replaces @app.callback
        self.app.callback(dash.dependencies.Output('live-graph', 'figure'), 
            dash.dependencies.Input('graph-update', 'n_intervals'))(self.make_update)
        
        self.app.layout = html.Div(
            [
                dcc.Graph(id = 'live-graph', animate = True),
                dcc.Interval(
                    id = 'graph-update',
                    interval = 1000,
                    n_intervals = 0
                ),
            ]
        )

    def make_update(self, input):
        return input
    
    def update(self,n):
        self.X.append(self.X[-1]+1)
        self.Y.append(self.Y[-1]+self.Y[-1] * random.uniform(-0.1,0.1))

        data = plotly.graph_objs.Scatter(
                x=list(self.X),
                y=list(self.Y),
                name='Scatter',
                mode= 'lines'
        )

        return {'data': [data],
                'layout' : go.Layout(xaxis=dict(range=[min(self.X),max(self.X)]),yaxis = dict(range = [min(self.Y),max(self.Y)]),)}

    def run(self):
        self.app.run(port = self.port,address = self.address)
        self.logger.info(f'Started live plot on http://localhost:{self.port}/')
        
