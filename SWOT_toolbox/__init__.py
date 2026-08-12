"""
SWOT toolbox package initialization.
"""

__version__ = '0.1.0'
__author__ = 'T. Faraon'

from . import SWOT_tools
from . import SWOT_loader

# [Dashboard] Import optionnel : SWOT_plot depend de bibliotheques de
# cartographie (geopandas, contextily, folium, plotly) qui ne sont pas
# necessaires cote serveur. En notebook, si ces bibliotheques sont
# installees, le comportement reste strictement identique a l'original.
try:
    from . import SWOT_plot
except ImportError:
    SWOT_plot = None
