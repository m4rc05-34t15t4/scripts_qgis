
from PyQt5.QtCore import *
from PyQt5.QtGui import *
"""
from qgis.core import *
from qgis.gui import *
from osgeo import ogr
import processing
import sys
"""

uri = QgsDataSourceUri()
uri.setConnection("localhost", "5432", "BA_M_1905_4_SO", "postgres", "admin")
filtro = """
    ST_INTERSECTS(geom, ST_GEOMFROMEWKT('SRID=31984;POLYGON((709225 9050006, 709225 9007193, 761450 9007193, 761450 9050006, 709225 9050006))'))
     AND  id in base.rio_l
    """
uri.setDataSource("cb", "tra_arruamento_l", "geom")
#uri.setDataSource("base", "rio_l", "geom", filtro, "primary_key_field")

vlayer = QgsVectorLayer(uri.uri(False), "tra_arruamento_l_teste", "postgres")
QgsProject.instance().addMapLayer(vlayer)

print(vlayer)