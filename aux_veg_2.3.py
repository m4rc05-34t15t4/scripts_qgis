from qgis.core import QgsProcessing
from qgis.core import QgsProcessingAlgorithm
from qgis.core import QgsProcessingMultiStepFeedback
from qgis.core import QgsProcessingParameterMapLayer
from qgis.core import QgsProcessingParameterMultipleLayers
from qgis.core import QgsProcessingParameterVectorDestination
from PyQt5.QtCore import QCoreApplication
import processing


class AuxVeg3(QgsProcessingAlgorithm):

    def initAlgorithm(self, config=None):
        # Set default layers
        default_moldura = 'moldura'
        default_centroide_vegetacao = 'centroide_vegetacao_p'
        default_delimitadores_vegetacao_linhas = ['delimitador_vegetacao_l', 'delimitador_massa_dagua_l', 'infra_barragem_l', 'infra_via_deslocamento_l', 'elemnat_trecho_drenagem_l', 'delimitador_area_construida_l']
        default_delimitadores_vegetacao_areas = ['Massa_Dagua','Area_Construida']

        self.addParameter(QgsProcessingParameterMultipleLayers('delimitadores_vegetacao_linhas', 'Delimitadores Linhas Vegetação', layerType=QgsProcessing.TypeVectorLine, defaultValue=default_delimitadores_vegetacao_linhas))
        self.addParameter(QgsProcessingParameterMultipleLayers('delimitadores_vegetacao_areas', 'Delimitadores Linhas Áreas', layerType=QgsProcessing.TypeVectorLine, defaultValue=default_delimitadores_vegetacao_areas))
        self.addParameter(QgsProcessingParameterMapLayer('moldura', 'Moldura', defaultValue=default_moldura))
        self.addParameter(QgsProcessingParameterMapLayer('centroide_vegetacao', 'Centroide Vegetação', defaultValue=default_centroide_vegetacao, types=[QgsProcessing.TypeVectorPoint]))
        self.addParameter(QgsProcessingParameterVectorDestination('output_polygons', 'Polígonos de Vegetação', type=QgsProcessing.TypeVectorPolygon))
        self.addParameter(QgsProcessingParameterVectorDestination('output_flags_polygons', 'Flags Áreas Vegetação', type=QgsProcessing.TypeVectorPolygon))

    def processAlgorithm(self, parameters, context, model_feedback):
        # Use a multi-step feedback, so that individual child algorithm progress reports are adjusted for the overall progress through the model
        feedback = QgsProcessingMultiStepFeedback(4, model_feedback)
        results = {}
        outputs = {}

        # Generate area_vegetacao using the polygon delimiters created above
        feedback.pushInfo('Generating area_vegetacao...')
        alg_params = {
            'ATTRIBUTE_BLACK_LIST': [''],
            'BOUNDARY_LINE_LAYER': None,
            'CHECK_INVALID_GEOMETRIES_ON_OUTPUT_POLYGONS': True,
            'CHECK_UNUSED_BOUNDARY_LINES': True,
            'CONSTRAINT_LINE_LAYERS': parameters['delimitadores_vegetacao_linhas'],
            'CONSTRAINT_POLYGON_LAYERS': parameters['delimitadores_vegetacao_areas'],
            'GEOGRAPHIC_BOUNDARY': parameters['moldura'],
            'GROUP_BY_SPATIAL_PARTITION': False,
            'INPUT_CENTER_POINTS': parameters['centroide_vegetacao'],
            'MERGE_OUTPUT_POLYGONS': False,
            'SELECTED': False,
            'SUPPRESS_AREA_WITHOUT_CENTROID_FLAG': False,
            'OUTPUT_POLYGONS': parameters['output_polygons'],
            'FLAGS': parameters['output_flags_polygons'],
            'INVALID_POLYGON_LOCATION': QgsProcessing.TEMPORARY_OUTPUT,
            'UNUSED_BOUNDARY_LINES': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['area_vegetacao'] = processing.run('dsgtools:buildpolygonsfromcenterpointsandboundariesalgorithm', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(3)
        if feedback.isCanceled():
            return {}

        return outputs

    def name(self):
        return 'aux_veg_2.3'

    def displayName(self):
        return 'Aux Veg 2.3'

    def group(self):
        return 'Aux Veg'

    def groupId(self):
        return 'aux_veg'

    def createInstance(self):
        return AuxVeg3()

    def shortHelpString(self):
        return QCoreApplication.translate(
            "AuxVeg3", 
            "Este algoritmo faz parte do conjunto de scripts para auxiliar na subfase "
            "Extração de Vegetação. Ele gera os polígonos de vegetação e os demais "
            "polígonos com erro, após o usuário já ter utilizado o Aux Veg 2, que gera os "
            "centroides concatenados por polígonos. Este script é essencial para a correção "
            "e validação dos dados de vegetação, garantindo que as áreas sejam corretamente "
            "mapeadas e que erros sejam identificados e corrigidos.\n\n"
            "Autoria de desenvolvimento de script Python: 2º Sgt Arruda do 3º CGEO."
        )

# Este script é parte das ferramentas desenvolvidas por Thiago Arruda, desenvolvedor Python especializado em cartografia e SIG.
