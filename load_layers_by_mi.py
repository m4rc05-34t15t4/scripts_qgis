# Este script carrega os vetores do banco de dados setado no código, baseado numa área delimitada setada no codigo, utilizando o id das áreas para que a mesma seja selecionada.
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

from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import (QgsProcessing,
                       QgsProcessingAlgorithm,
                       QgsProcessingParameterString,
                       QgsProcessingParameterBoolean,
                       QgsProcessingException)
from qgis import processing
import psycopg2
from qgis.core import (
    QgsVectorLayer, QgsProject, QgsDataSourceUri, QgsLayerTreeLayer, QgsWkbTypes, QgsGeometry
)
from qgis.utils import iface

class LoadLayersByMIAlgorithm(QgsProcessingAlgorithm):
    """
    This algorithm loads layers from a PostgreSQL database based on the
    given MI (Mapa Índice) and allows the user to select which types of
    geometries (points, lines, polygons) to load.
    """

    # Constants used to refer to parameters and outputs
    MI = 'MI'
    CARREGAR_PONTOS = 'CARREGAR_PONTOS'
    CARREGAR_LINHAS = 'CARREGAR_LINHAS'
    CARREGAR_POLIGONOS = 'CARREGAR_POLIGONOS'
    CARREGAR_AUX_MOLDURA = 'CARREGAR_AUX_MOLDURA'

    def initAlgorithm(self, config=None):
        """
        Define the inputs and output of the algorithm.
        """
        self.addParameter(
            QgsProcessingParameterString(
                self.MI,
                self.tr('Digite o valor do MI')
            )
        )
        
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.CARREGAR_PONTOS,
                self.tr('Carregar Pontos'),
                defaultValue=False
            )
        )

        self.addParameter(
            QgsProcessingParameterBoolean(
                self.CARREGAR_LINHAS,
                self.tr('Carregar Linhas'),
                defaultValue=False
            )
        )

        self.addParameter(
            QgsProcessingParameterBoolean(
                self.CARREGAR_POLIGONOS,
                self.tr('Carregar Polígonos'),
                defaultValue=False
            )
        )
        
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.CARREGAR_AUX_MOLDURA,
                self.tr('Carregar Aux Moldura'),
                defaultValue=False
            )
        )

    def name(self):
        """
        Returns the algorithm name, used for identifying the algorithm.
        """
        return 'load_layers_by_mi'

    def displayName(self):
        """
        Returns the translated algorithm name, which should be used for any
        user-visible display of the algorithm name.
        """
        return self.tr('Load Layers by MI')

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
        return self.tr("This algorithm loads layers from a PostgreSQL database based on the provided MI.")

    def tr(self, string):
        """
        Returns a translatable string with the self.tr() function.
        """
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):
        """
        Create a new instance of the algorithm.
        """
        return LoadLayersByMIAlgorithm()

    def get_connection(self):
        """
        Connect to the PostgreSQL database.
        """
        try:
            conn = psycopg2.connect(
                host="10.46.136.21",
                port="5432",
                dbname="insumos_pe",
                user="postgres",
                password="adminsap"
            )
            return conn
        except Exception as e:
            raise QgsProcessingException(f"Erro ao conectar ao banco de dados: {e}")

    def get_moldura_geom(self, mi):
        """
        Get the geometry of the moldura based on the MI.
        """
        conn = self.get_connection()
        if conn is None:
            return None, None

        try:
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT ST_AsText(ST_Buffer(geom, 0.0018)), geom
                FROM public.aux_moldura_a
                WHERE mi = %s
            """, (mi,))
            result = cursor.fetchone()
            cursor.close()
            conn.close()
            if result:
                return result[0], result[1]
            else:
                return None, None
        except Exception as e:
            raise QgsProcessingException(f"Erro ao obter a geometria da moldura: {e}")

    def get_all_tables(self):
        """
        Get all tables from the specified schemas.
        """
        conn = self.get_connection()
        if conn is None:
            return []
        
        schemas = ["GeoFTP_IBGE", "Outras_Fontes", "public"]
        all_tables = []
        try:
            cursor = conn.cursor()
            for schema in schemas:
                cursor.execute(f"""
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = '{schema}'
                """)
                tables = cursor.fetchall()
                for table in tables:
                    all_tables.append((schema, table[0]))
            
            cursor.close()
            conn.close()
        except Exception as e:
            raise QgsProcessingException(f"Erro ao obter tabelas: {e}")
        
        return all_tables

    def load_layers(self, tables, geom_wkt, selected_geom_types):
        """
        Load layers into QGIS with spatial filtering.
        """
        root = QgsProject.instance().layerTreeRoot()
        
        points_group = None
        lines_group = None
        polygons_group = None
        
        if "Points" in selected_geom_types:
            points_group = root.addGroup("Points")
        if "Lines" in selected_geom_types:
            lines_group = root.addGroup("Lines")
        if "Polygons" in selected_geom_types:
            polygons_group = root.addGroup("Polygons")

        for schema, table in tables:
            if table == "aux_moldura_a":
                continue
            
            uri = QgsDataSourceUri()
            uri.setConnection("10.46.136.21", "5432", "insumos_pe", "postgres", "adminsap")
            uri.setDataSource(schema, table, "geom", f"ST_Intersects(geom, ST_GeomFromText('{geom_wkt}', 4674))")

            layer_name = f"{schema}.{table}"
            layer = QgsVectorLayer(uri.uri(), layer_name, "postgres")
            
            if not layer.isValid():
                continue

            if layer.featureCount() == 0:
                continue

            geom_type = layer.geometryType()
            if (geom_type == QgsWkbTypes.PointGeometry and points_group is not None) or \
               (geom_type == QgsWkbTypes.LineGeometry and lines_group is not None) or \
               (geom_type == QgsWkbTypes.PolygonGeometry and polygons_group is not None):

                QgsProject.instance().addMapLayer(layer, False)
                if geom_type == QgsWkbTypes.PointGeometry:
                    points_group.insertChildNode(-1, QgsLayerTreeLayer(layer))
                elif geom_type == QgsWkbTypes.LineGeometry:
                    lines_group.insertChildNode(-1, QgsLayerTreeLayer(layer))
                elif geom_type == QgsWkbTypes.PolygonGeometry:
                    polygons_group.insertChildNode(-1, QgsLayerTreeLayer(layer))

    def load_moldura_layer(self, mi):
        """
        Load the moldura layer with filter on MI.
        """
        uri = QgsDataSourceUri()
        uri.setConnection("10.46.136.21", "5432", "insumos_pe", "postgres", "adminsap")
        uri.setDataSource("public", "aux_moldura_a", "geom", f"mi = '{mi}'")

        layer = QgsVectorLayer(uri.uri(), "aux_moldura_a", "postgres")

        if not layer.isValid():
            raise QgsProcessingException("Falha ao carregar a camada aux_moldura_a.")

        if layer.featureCount() == 0:
            raise QgsProcessingException("A camada aux_moldura_a não possui elementos.")

        QgsProject.instance().addMapLayer(layer, False)
        root = QgsProject.instance().layerTreeRoot()
        aux_group = root.addGroup("Moldura")
        aux_group.insertChildNode(-1, QgsLayerTreeLayer(layer))
        return layer

    def processAlgorithm(self, parameters, context, feedback):
        """
        The processing itself takes place here.
        """
        feedback.pushInfo('Iniciando processamento...')
        
        mi = self.parameterAsString(parameters, self.MI, context)
        feedback.pushInfo(f'MI: {mi}')
        
        carregar_pontos = self.parameterAsBool(parameters, self.CARREGAR_PONTOS, context)
        feedback.pushInfo(f'Carregar Pontos: {carregar_pontos}')
        
        carregar_linhas = self.parameterAsBool(parameters, self.CARREGAR_LINHAS, context)
        feedback.pushInfo(f'Carregar Linhas: {carregar_linhas}')
        
        carregar_poligonos = self.parameterAsBool(parameters, self.CARREGAR_POLIGONOS, context)
        feedback.pushInfo(f'Carregar Polígonos: {carregar_poligonos}')
        
        carregar_aux_moldura = self.parameterAsBool(parameters, self.CARREGAR_AUX_MOLDURA, context)
        feedback.pushInfo(f'Carregar Aux Moldura: {carregar_aux_moldura}')

        geom_wkt, geom = self.get_moldura_geom(mi)
        if not geom_wkt:
            feedback.reportError('Não foi possível obter a geometria da moldura.')
            raise QgsProcessingException("Não foi possível obter a geometria da moldura.")

        feedback.pushInfo('Geometria da moldura obtida com sucesso.')

        # Definir a área de trabalho do QGIS como a área do buffer
        try:
            geom = QgsGeometry.fromWkt(geom_wkt)
            iface.mapCanvas().setExtent(geom.boundingBox())
        except Exception as e:
            feedback.reportError('Erro ao definir a área de trabalho do QGIS.')
            raise QgsProcessingException(f"Erro ao definir a área de trabalho do QGIS: {e}")

        feedback.pushInfo('Área de trabalho definida.')

        # Carregar a camada aux_moldura_a com filtro no MI se a opção estiver marcada
        if carregar_aux_moldura:
            try:
                moldura_layer = self.load_moldura_layer(mi)
                feedback.pushInfo('Camada aux_moldura_a carregada com sucesso.')
            except Exception as e:
                feedback.reportError('Falha ao carregar a camada aux_moldura_a.')
                raise QgsProcessingException(f"Falha ao carregar a camada aux_moldura_a: {e}")

        # Selecionar tipos de geometria a carregar
        selected_geom_types = []
        if carregar_pontos:
            selected_geom_types.append("Points")
        if carregar_linhas:
            selected_geom_types.append("Lines")
        if carregar_poligonos:
            selected_geom_types.append("Polygons")

        if not selected_geom_types:
            feedback.reportError('Nenhum tipo de geometria selecionado.')
            raise QgsProcessingException("Nenhum tipo de geometria selecionado.")

        tables = self.get_all_tables()
        if not tables:
            feedback.reportError('Nenhuma tabela encontrada nos esquemas especificados.')
            raise QgsProcessingException("Nenhuma tabela encontrada nos esquemas especificados.")
        
        self.load_layers(tables, geom_wkt, selected_geom_types)

        feedback.pushInfo('Todas as camadas foram carregadas com sucesso.')

        return {}
