#Este script salva os nomes das camadas carregadas no qgis, por grupo de geometrias(pontos, linhas e poligonos)
# -*- coding: utf-8 -*-

from qgis.core import QgsProject, QgsProcessingAlgorithm, QgsProcessingParameterFileDestination, QgsWkbTypes
from qgis.PyQt.QtCore import QCoreApplication

class SaveLayerNamesAlgorithm(QgsProcessingAlgorithm):
    OUTPUT_POINTS = 'OUTPUT_POINTS'
    OUTPUT_LINES = 'OUTPUT_LINES'
    OUTPUT_AREAS = 'OUTPUT_AREAS'

    def tr(self, string):
        return QCoreApplication.translate('SaveLayerNamesAlgorithm', string)

    def createInstance(self):
        return SaveLayerNamesAlgorithm()

    def name(self):
        return 'savelayernamingroups'

    def displayName(self):
        return self.tr('Save Layer Names by Geometry Type')

    def group(self):
        return self.tr('Layer Processing')

    def groupId(self):
        return 'layerprocessing'

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterFileDestination(
                self.OUTPUT_POINTS,
                self.tr('Output file for point layers'),
                fileFilter='Text files (*.txt)'
            )
        )
        self.addParameter(
            QgsProcessingParameterFileDestination(
                self.OUTPUT_LINES,
                self.tr('Output file for line layers'),
                fileFilter='Text files (*.txt)'
            )
        )
        self.addParameter(
            QgsProcessingParameterFileDestination(
                self.OUTPUT_AREAS,
                self.tr('Output file for area layers'),
                fileFilter='Text files (*.txt)'
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        output_points = self.parameterAsFile(parameters, self.OUTPUT_POINTS, context)
        output_lines = self.parameterAsFile(parameters, self.OUTPUT_LINES, context)
        output_areas = self.parameterAsFile(parameters, self.OUTPUT_AREAS, context)

        project = QgsProject.instance()
        root = project.layerTreeRoot()
        all_layers = self.get_layer_names(root)

        points = set()
        lines = set()
        areas = set()

        for layer_name in all_layers:
            layer = project.mapLayer(layer_name)
            if layer is None:
                continue
            geometry_type = layer.geometryType()
            if geometry_type == QgsWkbTypes.PointGeometry:
                points.add(layer.name())
            elif geometry_type == QgsWkbTypes.LineGeometry:
                lines.add(layer.name())
            elif geometry_type == QgsWkbTypes.PolygonGeometry:
                areas.add(layer.name())

        with open(output_points, 'w') as file:
            file.write(','.join(points))

        with open(output_lines, 'w') as file:
            file.write(','.join(lines))

        with open(output_areas, 'w') as file:
            file.write(','.join(areas))

        return {self.OUTPUT_POINTS: output_points, self.OUTPUT_LINES: output_lines, self.OUTPUT_AREAS: output_areas}

    def get_layer_names(self, group):
        layer_names = []
        for item in group.findLayers():
            layer_names.append(item.layerId())
        for subgroup in group.findGroups():
            layer_names.extend(self.get_layer_names(subgroup))
        return layer_names

