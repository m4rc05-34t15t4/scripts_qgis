from qgis.core import QgsProcessing
from qgis.core import QgsProcessingAlgorithm
from qgis.core import QgsProcessingMultiStepFeedback
from qgis.core import QgsProcessingParameterMultipleLayers
from qgis.core import QgsProcessingParameterMapLayer
from PyQt5.QtCore import QCoreApplication
import processing

class AuxVeg1(QgsProcessingAlgorithm):

    def initAlgorithm(self, config=None):
        # Define default layers for intersection and frame
        default_intersection_layers = ['elemnat_trecho_drenagem_l', 'infra_via_deslocamento_l','delimitador_area_construida_l',
        'delimitador_massa_dagua_l','delimitador_vegetacao_l','infra_barragem_l']
        default_moldura_layer = 'moldura'

        self.addParameter(QgsProcessingParameterMultipleLayers(
            'linhasparaintersecao', 
            'Lines for Intersection', 
            layerType=QgsProcessing.TypeVectorLine, 
            defaultValue=default_intersection_layers
        ))
        self.addParameter(QgsProcessingParameterMapLayer(
            'moldura', 
            'Frame', 
            defaultValue=default_moldura_layer, 
            types=[QgsProcessing.TypeVectorPolygon]
        ))

    def processAlgorithm(self, parameters, context, model_feedback):
        # Use multi-step feedback to adjust the overall progress through the model
        feedback = QgsProcessingMultiStepFeedback(1, model_feedback)
        results = {}
        outputs = {}

        # Unshared Vertices
        alg_params = {
            'GEOGRAPHIC_BOUNDARY': parameters['moldura'],
            'INPUT_LINES': parameters['linhasparaintersecao'],
            'INPUT_POINTS': None,
            'INPUT_POLYGONS': None,
            'SEARCH_RADIUS': 1e-05,
            'SELECTED': False
        }
        outputs['UnsharedVertices'] = processing.run(
            'dsgtools:addunsharedvertexonintersectionsalgorithm', 
            alg_params, 
            context=context, 
            feedback=feedback, 
            is_child_algorithm=True
        )
        return results

    def name(self):
        return 'aux_veg_1'

    def displayName(self):
        return 'Aux Veg 1'

    def group(self):
        return 'Aux Veg'

    def groupId(self):
        return 'aux_veg'

    def createInstance(self):
        return AuxVeg1()

    def shortHelpString(self):
        return QCoreApplication.translate(
            "AuxVeg1", 
            "Este script utiliza algoritmos do DSG Tools para gerar pontos de "
            "interseção onde não existem, especificamente entre as linhas de drenagem "
            "e as vias de deslocamento. Este processo é essencial para garantir a "
            "precisão topológica das interseções, permitindo uma análise espacial mais "
            "coerente e a correção de inconsistências nos dados geoespaciais.\n\n"
            "Autoria de desenvolvimento de script Python: 2º Sgt Arruda do 3º CGEO."
    )


# This script is part of the tools developed by Thiago Arruda, Python developer specializing in cartography and GIS.
