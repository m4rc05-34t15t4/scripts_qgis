from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingMultiStepFeedback,
    QgsProcessingParameterMapLayer,
    QgsProcessingParameterMultipleLayers,
    QgsProcessingParameterFeatureSink,
    QgsProject,
    QgsVectorLayer,
    QgsProcessingUtils
)
from PyQt5.QtCore import QCoreApplication
import processing
import os


class AuxVeg21(QgsProcessingAlgorithm):

    CENTROIDE_AREA_CONSTRUIDA = 'centroide_area_construida'
    CENTROIDE_MASSA_DAGUA = 'centroide_massa_dagua'
    DELIMITADORES_LINHAS_MASSA_DAGUA = 'delimitadores_linhas_massa_dagua'
    DELIMITADORES_LINHAS_AREA_CONSTRUIDA = 'delimitadores_linhas_area_construida'
    MOLDURA = 'moldura'
    OUTPUT_AREA_CONSTRUIDA = 'output_area_construida'
    OUTPUT_MASSA_DAGUA = 'output_massa_dagua'

    def initAlgorithm(self, config=None):
        default_centroide_area_construida = 'centroide_area_edificada_p'
        default_centroide_massa_dagua = 'centroide_massa_dagua_p'
        default_delimitadores_massa = ['delimitador_massa_dagua_l', 'infra_barragem_l', 'infra_via_deslocamento_l']
        default_delimitadores_area_construida = 'delimitador_area_edificada_l'
        default_moldura = 'aux_moldura_a'

        self.addParameter(QgsProcessingParameterMapLayer(self.CENTROIDE_AREA_CONSTRUIDA, 'Centroide Area Construida', defaultValue=default_centroide_area_construida, types=[QgsProcessing.TypeVectorPoint]))
        self.addParameter(QgsProcessingParameterMapLayer(self.CENTROIDE_MASSA_DAGUA, 'Centroide Massa Dagua', defaultValue=default_centroide_massa_dagua, types=[QgsProcessing.TypeVectorPoint]))
        self.addParameter(QgsProcessingParameterMultipleLayers(self.DELIMITADORES_LINHAS_MASSA_DAGUA, 'Delimitadores Linhas Massa Dagua', layerType=QgsProcessing.TypeVectorLine, defaultValue=default_delimitadores_massa))
        self.addParameter(QgsProcessingParameterMultipleLayers(self.DELIMITADORES_LINHAS_AREA_CONSTRUIDA, 'Delimitadores Linhas Area Construida', layerType=QgsProcessing.TypeVectorLine, defaultValue=default_delimitadores_area_construida))
        self.addParameter(QgsProcessingParameterMapLayer(self.MOLDURA, 'Moldura', defaultValue=default_moldura))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT_AREA_CONSTRUIDA, 'Output Area_construida', type=QgsProcessing.TypeVectorPolygon, createByDefault=True, defaultValue=None))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT_MASSA_DAGUA, 'Output Massa_Dagua', type=QgsProcessing.TypeVectorPolygon, createByDefault=True, defaultValue=None))

    def processAlgorithm(self, parameters, context, model_feedback):
        feedback = QgsProcessingMultiStepFeedback(2, model_feedback)
        results = {}
        outputs = {}

        # Generate area_construida polygon delimiters
        area_construida_sink, area_construida_path = self.generatePolygons(
            parameters,
            context,
            feedback,
            'area_construida',
            self.CENTROIDE_AREA_CONSTRUIDA,
            self.DELIMITADORES_LINHAS_AREA_CONSTRUIDA,
            self.OUTPUT_AREA_CONSTRUIDA
        )

        outputs['area_construida'] = area_construida_sink

        if feedback.isCanceled():
            return {}

        # Generate massa_dagua polygon delimiters
        massa_dagua_sink, massa_dagua_path = self.generatePolygons(
            parameters,
            context,
            feedback,
            'massa_dagua',
            self.CENTROIDE_MASSA_DAGUA,
            self.DELIMITADORES_LINHAS_MASSA_DAGUA,
            self.OUTPUT_MASSA_DAGUA
        )

        outputs['massa_dagua'] = massa_dagua_sink

        if feedback.isCanceled():
            return {}

        results[self.OUTPUT_AREA_CONSTRUIDA] = area_construida_path
        results[self.OUTPUT_MASSA_DAGUA] = massa_dagua_path

        self.loadLayerToProject(area_construida_path, 'Area_Construida')
        self.loadLayerToProject(massa_dagua_path, 'Massa_Dagua')

        return results

    def generatePolygons(self, parameters, context, feedback, name, centroide_param, delimitadores_param, output_param):
        feedback.pushInfo(f'Generating {name} polygon delimiters...')
        temp_output = os.path.normpath(os.path.join(QgsProcessingUtils.tempFolder(), f'{name}.shp'))
        
        # Remover o arquivo existente, se houver
        if os.path.exists(temp_output):
            os.remove(temp_output)
            for ext in ['.shx', '.dbf', '.prj', '.cpg']:
                aux_file = temp_output.replace('.shp', ext)
                if os.path.exists(aux_file):
                    os.remove(aux_file)

        alg_params = {
            'ATTRIBUTE_BLACK_LIST': [''],
            'BOUNDARY_LINE_LAYER': None,
            'CHECK_INVALID_GEOMETRIES_ON_OUTPUT_POLYGONS': True,
            'CHECK_UNUSED_BOUNDARY_LINES': True,
            'CONSTRAINT_LINE_LAYERS': parameters[delimitadores_param],
            'CONSTRAINT_POLYGON_LAYERS': None,
            'GEOGRAPHIC_BOUNDARY': parameters[self.MOLDURA],
            'GROUP_BY_SPATIAL_PARTITION': False,
            'INPUT_CENTER_POINTS': parameters[centroide_param],
            'MERGE_OUTPUT_POLYGONS': False,
            'SELECTED': False,
            'SUPPRESS_AREA_WITHOUT_CENTROID_FLAG': False,
            'FLAGS': QgsProcessing.TEMPORARY_OUTPUT,
            'INVALID_POLYGON_LOCATION': QgsProcessing.TEMPORARY_OUTPUT,
            'OUTPUT_POLYGONS': temp_output,
            'UNUSED_BOUNDARY_LINES': QgsProcessing.TEMPORARY_OUTPUT
        }
        result = processing.run('dsgtools:buildpolygonsfromcenterpointsandboundariesalgorithm', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
        return result['OUTPUT_POLYGONS'], temp_output

    def loadLayerToProject(self, path, layer_name):
        path = os.path.normpath(path)
        layer = QgsVectorLayer(path, layer_name, 'ogr')
        if layer.isValid():
            QgsProject.instance().addMapLayer(layer)
        else:
            raise ValueError(f'Layer {layer_name} not found at {path}')

    def name(self):
        return 'aux_veg_21'

    def displayName(self):
        return 'Aux Veg 2.1'

    def group(self):
        return 'Aux Veg'

    def groupId(self):
        return 'aux_veg'

    def createInstance(self):
        return AuxVeg21()

    def shortHelpString(self):
        return QCoreApplication.translate(
            "AuxVeg21", 
            "Este script gera os delimitadores de polígonos para áreas construídas e massas d'água utilizando algoritmos do DSG Tools."
        )
