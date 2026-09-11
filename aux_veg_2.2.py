from qgis.core import QgsProcessing
from qgis.core import QgsProcessingAlgorithm
from qgis.core import QgsProcessingMultiStepFeedback
from qgis.core import QgsProcessingParameterMapLayer
from qgis.core import QgsProcessingParameterMultipleLayers
from qgis.core import QgsProcessingParameterFeatureSink
from PyQt5.QtCore import QCoreApplication
import processing


class AuxVeg2(QgsProcessingAlgorithm):

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
        self.addParameter(QgsProcessingParameterFeatureSink('centroides_filtrados_veg', 'Centroides Filtrados Vegetação', type=QgsProcessing.TypeVectorAnyGeometry, createByDefault=True, defaultValue=None))

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
            'FLAGS': QgsProcessing.TEMPORARY_OUTPUT,
            'INVALID_POLYGON_LOCATION': QgsProcessing.TEMPORARY_OUTPUT,
            'OUTPUT_POLYGONS': QgsProcessing.TEMPORARY_OUTPUT,
            'UNUSED_BOUNDARY_LINES': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['area_vegetacao'] = processing.run('dsgtools:buildpolygonsfromcenterpointsandboundariesalgorithm', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(3)
        if feedback.isCanceled():
            return {}

        # Intersect Points with Polygons
        feedback.pushInfo('Intersecting points with polygons...')
        alg_params = {
            'POINTS': parameters['centroide_vegetacao'],
            'POLYGONS': outputs['area_vegetacao']['OUTPUT_POLYGONS'],
            'OUTPUT': parameters['centroides_filtrados_veg']
        }
        outputs['intersect_points_with_polygons'] = processing.run('script:intersect_points_with_polygons', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
        results['centroides_filtrados_veg'] = outputs['intersect_points_with_polygons']['OUTPUT']

        feedback.setCurrentStep(4)
        if feedback.isCanceled():
            return {}

        return results

    def name(self):
        return 'aux_veg_2.2'

    def displayName(self):
        return 'Aux Veg 2.2'

    def group(self):
        return 'Aux Veg'

    def groupId(self):
        return 'aux_veg'

    def createInstance(self):
        return AuxVeg2()

    def shortHelpString(self):
        return QCoreApplication.translate(
            "AuxVeg2", 
            "Este script utiliza algoritmos do DSG Tools para criar centroides "
            "concatenados (um centroide por área) das áreas de vegetação. Os centroides "
            "gerados são fundamentais para análises posteriores, permitindo a identificação "
            "precisa do centro geométrico de cada polígono de vegetação, facilitando assim a "
            "gestão e o monitoramento dessas áreas.\n\n"
            "Autoria de desenvolvimento de script Python: 2º Sgt Arruda do 3º CGEO."
        )


# Este script é parte das ferramentas desenvolvidas por Thiago Arruda, desenvolvedor Python especializado em cartografia e SIG.
