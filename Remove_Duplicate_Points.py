#este script remove os centroides(pontos), duplicados ou mais, que estão dentro do mesmo poligono, desenvolvido para ajudar na produção cartográfica
# -*- coding: utf-8 -*-

"""
***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 2 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************
"""

from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.core import (QgsProcessing,
                       QgsProcessingAlgorithm,
                       QgsProcessingParameterFeatureSource,
                       QgsProcessingParameterFeatureSink,
                       QgsProcessingException,
                       QgsFeatureSink,
                       QgsFeature,
                       QgsGeometry,
                       QgsWkbTypes,
                       QgsSpatialIndex,
                       QgsField,
                       QgsFields,
                       QgsFeatureRequest)
from qgis import processing

class IntersectPointsWithPolygonsAlgorithm(QgsProcessingAlgorithm):
    """
    This algorithm creates a new layer of points that intersect each polygon and
    adds the FID of the polygon to the attribute table of this new layer of points,
    along with the original attributes of each point.
    It ensures that only one point per polygon FID is kept and includes points
    that are outside the polygons.
    """

    # Constants used to refer to parameters and outputs
    POLYGONS = 'POLYGONS'
    POINTS = 'POINTS'
    OUTPUT = 'OUTPUT'

    def initAlgorithm(self, config=None):
        """
        Define the inputs and output of the algorithm.
        """
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.POLYGONS,
                self.tr('Select Polygon Layer'),
                [QgsProcessing.TypeVectorPolygon]
            )
        )
        
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.POINTS,
                self.tr('Select Points Layer'),
                [QgsProcessing.TypeVectorPoint]
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT,
                self.tr('Filtered Centroids')
            )
        )

    def name(self):
        """
        Returns the algorithm name, used for identifying the algorithm.
        """
        return 'intersect_points_with_polygons'

    def displayName(self):
        """
        Returns the translated algorithm name, which should be used for any
        user-visible display of the algorithm name.
        """
        return self.tr('Intersect Points with Polygons')

    def group(self):
        """
        Returns the name of the group this algorithm belongs to.
        """
        return self.tr('Vector Processing')

    def groupId(self):
        """
        Returns the unique ID of the group this algorithm belongs to.
        """
        return 'vectorprocessing'

    def shortHelpString(self):
        """
        Returns a localised short helper string for the algorithm.
        """
        return self.tr("This algorithm creates a new layer of points that intersect each polygon and adds the FID of the polygon to the attribute table of this new layer of points, along with the original attributes of each point. It ensures that only one point per polygon FID is kept and includes points that are outside the polygons.")

    def tr(self, string):
        """
        Returns a translatable string with the self.tr() function.
        """
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):
        """
        Create a new instance of the algorithm.
        """
        return IntersectPointsWithPolygonsAlgorithm()

    def processAlgorithm(self, parameters, context, feedback):
        """
        The processing itself takes place here.
        """
        polygons_layer = self.parameterAsSource(parameters, self.POLYGONS, context)
        points_layer = self.parameterAsSource(parameters, self.POINTS, context)

        if polygons_layer is None or points_layer is None:
            raise QgsProcessingException(self.invalidSourceError(parameters, self.POLYGONS))

        # Prepare the output layer
        fields = points_layer.fields()
        (sink, dest_id) = self.parameterAsSink(parameters, self.OUTPUT, context,
                                               fields, QgsWkbTypes.Point, points_layer.sourceCrs())

        if sink is None:
            raise QgsProcessingException(self.invalidSinkError(parameters, self.OUTPUT))

        feedback.pushInfo('Iniciando processamento...')

        # Create a spatial index for the points layer
        feedback.pushInfo('Criando índice espacial para a camada de pontos...')
        point_index = QgsSpatialIndex(points_layer.getFeatures())

        feedback.pushInfo('Iterando sobre os polígonos...')
        # Create a dictionary to keep track of unique points by polygon FID
        unique_points = {}
        points_in_polygons = set()

        # Iterate through polygons
        for polygon in polygons_layer.getFeatures():
            polygon_geom = polygon.geometry()
            if not polygon_geom.isGeosValid():
                feedback.reportError(f'Polígono inválido encontrado com ID {polygon.id()}')
                continue
            
            point_ids = point_index.intersects(polygon_geom.boundingBox())

            # Filter points within the polygon
            points_within_polygon = [f for f in points_layer.getFeatures(QgsFeatureRequest().setFilterFids(point_ids)) if f.geometry().intersects(polygon_geom)]
            
            feedback.pushInfo(f'Processando polígono ID {polygon.id()} com {len(points_within_polygon)} pontos dentro dele...')
            for point in points_within_polygon:
                points_in_polygons.add(point.id())
                if polygon.id() not in unique_points:
                    unique_points[polygon.id()] = point

        feedback.pushInfo('Adicionando pontos únicos à camada de saída...')
        # Add points that are within polygons
        for fid, point in unique_points.items():
            new_feature = QgsFeature()
            new_feature.setGeometry(point.geometry())
            new_feature.setAttributes(point.attributes())
            sink.addFeature(new_feature, QgsFeatureSink.FastInsert)

        # Add points that are outside polygons
        feedback.pushInfo('Adicionando pontos fora dos polígonos...')
        for point in points_layer.getFeatures():
            if point.id() not in points_in_polygons:
                new_feature = QgsFeature()
                new_feature.setGeometry(point.geometry())
                new_feature.setAttributes(point.attributes())
                sink.addFeature(new_feature, QgsFeatureSink.FastInsert)

        feedback.pushInfo('Processamento concluído. Nova camada criada com pontos únicos.')

        return {self.OUTPUT: dest_id}
