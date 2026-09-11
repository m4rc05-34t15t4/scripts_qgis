from PyQt5.QtCore import QCoreApplication, QVariant
import processing
from qgis.core import QgsProject, QgsFeature, QgsGeometry, QgsPointXY, QgsVectorLayer, QgsField, QgsWkbTypes, QgsGeometry, QgsSpatialIndex, QgsProcessingAlgorithm, QgsApplication
from qgis.PyQt.QtCore import QVariant, Qt
import math
from qgis.PyQt.QtWidgets import QProgressDialog

class AuxVeg1(QgsProcessingAlgorithm):

    def initAlgorithm(self):
        pass

    def processAlgorithm(self, parameters, context, model_feedback):

        #BARRA DE PROGRESSO

        def add_progresso(progress, i):
            progress.setValue(i)
            # Atualiza a interface gráfica para mostrar o progresso
            QgsApplication.processEvents()

            if i >= 100:
                progress.close()

        # Configura a barra de progresso
        progresso = QProgressDialog("Executando passos...", "Cancelar", 0, 100)
        progresso.setWindowTitle("Progresso do Script")
        progresso.setWindowModality(Qt.WindowModal)
        progresso.setMinimumDuration(0)
        progresso.setCancelButton(None)
        progresso.show()

        add_progresso(progresso, 0)

        """
        for i in range(100):

            progresso.setValue(i)
            
            # Atualiza a interface gráfica para mostrar o progresso
            QgsApplication.processEvents()
        progresso.close()
        """

        #COBER TURA TERRESTRE DELIMITADORES
        
        #VARIAVEIS

        vertices_coincidentes = "Vertices_Coincidentes"
        pt_vertices = "Pontos_Vertices"
        layer_delimitadores_list = [
            'delimitador_vegetacao_l',
            'delimitador_massa_dagua_l',
            'delimitador_area_construida_l',
            'delimitador_area_sem_dados_l',
            'delimitador_elemento_hidrografico_l',
            'delimitador_limite_especial_l',
        ]
        list_camadas_para_nao_ter_flags = ['aux_moldura_a']
        lista_camadas_inserir_vertices = [
            'elemnat_trecho_drenagem_l',
            'infra_via_deslocamento_l',
            'infra_barragem_l',
            'infra_ferrovia_l',
            'infra_vala_l',
        ]  
        list_verificar_toques = lista_camadas_inserir_vertices + list_camadas_para_nao_ter_flags
        list_gerar_vertices_coincidentes = layer_delimitadores_list + lista_camadas_inserir_vertices

        #FUNCOES

        def gerar_vertices_coincidentes(layer_names):

            # Carregar as camadas
            layers = {name: QgsProject.instance().mapLayersByName(name)[0] for name in layer_names}

            # Verificar se todas as camadas foram encontradas
            if not all(layers.values()):
                print("Uma ou mais camadas não foram encontradas. Verifique os nomes das camadas.")
            else:
                # Criar uma camada de pontos para os vértices
                point_layer = QgsVectorLayer("Point?crs=EPSG:4326", "Vertices_Coincidentes", "memory")
                point_layer_data = point_layer.dataProvider()
                
                # Adicionar campos para a nova camada de pontos
                point_layer_data.addAttributes([
                    QgsField("layer_ids", QVariant.String),
                    QgsField("feature_ids", QVariant.String),
                    QgsField("vertex_indices", QVariant.String),
                    QgsField("total_vertices", QVariant.String),
                    QgsField("total_vertices_coincidentes", QVariant.Int)  # Novo atributo
                ])
                point_layer.updateFields()

                # Dicionário para armazenar vértices e suas informações
                vertex_info = {}

                # Iterar sobre as camadas e extrair vértices
                for layer_name, layer in layers.items():
                    for feature in layer.getFeatures():
                        #print(str(feature['id']), str(feature['data_criacao']))
                        geom = feature.geometry()
                        if geom.isEmpty():
                            continue
                        
                        # Obter os vértices da geometria como pontos
                        vertices = []

                        # Verificar o tipo de geometria
                        if geom.type() == QgsWkbTypes.LineGeometry:
                            # Obter vértices para geometria do tipo linha
                            if geom.isMultipart():
                                for part in geom.asMultiPolyline():
                                    vertices.extend(part)  # Manter como QgsPointXY
                            else:
                                vertices = geom.asPolyline()  # Manter como QgsPointXY

                        elif geom.type() == QgsWkbTypes.PolygonGeometry:
                            # Converter o polígono em uma ou mais linhas
                            if geom.isMultipart():
                                # Processar cada parte do polígono multipart
                                for part in geom.asMultiPolygon():
                                    for ring in part:  # Processar cada anel do polígono
                                        vertices.extend(ring)  # Manter como QgsPointXY
                            else:
                                # Processar o polígono de única parte
                                for ring in geom.asPolygon():  # Para cada anel
                                    vertices.extend(ring)  # Manter como QgsPointXY

                        # Calcular o total de vértices
                        total_vertices = len(vertices)

                        # Armazenar informações sobre os vértices
                        for index, vertex in enumerate(vertices):
                            vertex_key = (vertex.x(), vertex.y())  # Usar coordenadas como chave
                            if vertex_key not in vertex_info:
                                vertex_info[vertex_key] = []
                            vertex_info[vertex_key].append({
                                "layer_id": layer_name,
                                "feature_id": feature['id'],
                                "vertex_index": index,
                                "total_vertices": total_vertices
                            })

                # Filtrar apenas os vértices que estão presentes em mais de uma camada
                for vertex, infos in vertex_info.items():
                    if len(infos) > 1:  # Verifica se está presente em mais de uma camada
                        # Adicionar ponto à nova camada
                        point_feature = QgsFeature()
                        point_feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(vertex[0], vertex[1])))

                        # Preparar listas para atributos
                        layer_ids = []
                        feature_ids = []
                        vertex_indices = []
                        total_vertices = []

                        # Coletar informações de cada camada
                        for info in infos:
                            layer_ids.append(info["layer_id"])
                            feature_ids.append(str(info["feature_id"]))
                            vertex_indices.append(str(info["vertex_index"]))
                            total_vertices.append(str(info["total_vertices"]))

                        # Definir atributos do ponto
                        point_feature.setAttributes([
                            ', '.join(layer_ids),
                            ', '.join(feature_ids),
                            ', '.join(vertex_indices),
                            ', '.join(total_vertices),
                            len(infos)  # Total de vértices coincidentes
                        ])

                        point_layer_data.addFeature(point_feature)

                # Adicionar a camada de pontos ao projeto
                QgsProject.instance().addMapLayer(point_layer)
                print("Camada 'Vertices_Coincidentes' criada com sucesso.")


        def gerar_pontos_extremidades(layer_delimitadores_list, vertices_coincidentes, pt_vertices):

            vertices_layer = QgsProject.instance().mapLayersByName(vertices_coincidentes)[0]

            # Verificar se as camadas foram encontradas
            if not vertices_layer:
                print("Camada ", vertices_coincidentes, " não encontrada!" )
            else:
                # Criar um conjunto de vértices da camada Vertices_Coincidentes
                vertices_set = set()
                for feature in vertices_layer.getFeatures():
                    geom = feature.geometry()
                    if geom.isEmpty() or not geom.isMultipart():
                        continue

                    for point in geom.asMultiPoint():
                        vertices_set.add((point.x(), point.y()))

                # Criar uma nova camada de pontos para armazenar os novos vértices
                points_layer = QgsVectorLayer('Point?crs=EPSG:4326', pt_vertices, 'memory')
                provider = points_layer.dataProvider()

                # Adicionar campos à nova camada
                provider.addAttributes([
                    QgsField('id', QVariant.Int),  # ID da camada origem como String
                    QgsField('id_origem', QVariant.String),  # ID da camada origem como String
                    QgsField('camada_origem', QVariant.String),
                    QgsField('index_vertice', QVariant.String)
                ])
                points_layer.updateFields()

                print("Pontos de Extremedidade: ")
                
                i = 1
                for layer_name in layer_delimitadores_list:

                    # Carregar as camadas
                    vegetacao_layer = QgsProject.instance().mapLayersByName(layer_name)[0]
                    
                    if not vegetacao_layer:
                        print("Uma ou ambas as camadas não foram encontradas.")
                    
                    else:
                        # Extrair primeiro e último vértice da camada delimitador_vegetacao_l
                        for feature in vegetacao_layer.getFeatures():
                            geom = feature.geometry()
                            if geom.isEmpty():
                                continue
                            
                            # Obter os vértices da geometria como pontos
                            if geom.isMultipart():
                                vertices = geom.asMultiPolyline()[0]  # Considerar apenas a primeira parte
                            else:
                                vertices = geom.asPolyline()

                            # Extraindo o primeiro e o último vértice
                            first_vertex = vertices[0]
                            last_vertex = vertices[-1]

                            # Verificar se o primeiro vértice não está nos vértices coincidentes
                            if (first_vertex.x(), first_vertex.y()) not in vertices_set:
                                new_feature = QgsFeature()
                                new_feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(first_vertex.x(), first_vertex.y())))
                                new_feature.setAttributes([i, feature['id'], layer_name, 'primeiro'])  # ID da camada origem como String e índice do vértice
                                provider.addFeature(new_feature)
                                i += 1

                            # Verificar se o último vértice não está nos vértices coincidentes
                            if (last_vertex.x(), last_vertex.y()) not in vertices_set:
                                new_feature = QgsFeature()
                                new_feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(last_vertex.x(), last_vertex.y())))
                                new_feature.setAttributes([i, feature['id'], layer_name, 'ultimo'])  # ID da camada origem como String e índice do vértice
                                provider.addFeature(new_feature)
                                i += 1

                        # Adicionar a nova camada ao projeto
                        QgsProject.instance().addMapLayer(points_layer)

                        print(layer_name, ": ", points_layer.featureCount())

        def remover_feicoes_selecionadas(layer_vertices):
            # Iniciar o modo de edição para remover feições selecionadas
            layer_vertices.startEditing()
            for feature in layer_vertices.selectedFeatures():
                layer_vertices.deleteFeature(feature.id())
            # Salvar e encerrar o modo de edição
            layer_vertices.commitChanges()
            # Limpe a seleção após a remoção
            layer_vertices.removeSelection()
            return True

        # Função para converter metros para graus com base na latitude
        def metros_para_graus(metros, latitude):
            return metros / (111320 * math.cos(math.radians(latitude)))

        def deletar_vertices_ok(pt_vertices, vertices_coincidentes, list_layer_aux=[]):

            # Obtenha as camadas "Pontos_Vertices", "Vertices_Coincidentes"
            layer_vertices = QgsProject.instance().mapLayersByName(pt_vertices)
            layer_intersecoes = QgsProject.instance().mapLayersByName(vertices_coincidentes)
            
            # Verifique se as camadas existem
            if not layer_vertices:
                print("Camada ",pt_vertices, " não encontrada.")
            elif not layer_intersecoes:
                print("Camada ", vertices_coincidentes, " não encontrada.")
            else:
                # Obter a primeira camada encontrada
                layer_vertices = layer_vertices[0]
                layer_intersecoes = layer_intersecoes[0]

                # Execute a seleção por localização para selecionar os vértices que coincidem
                processing.run("native:selectbylocation", {
                    'INPUT': layer_vertices,
                    'PREDICATE': [0], # [0] corresponde ao operador "Igual a" (Equals)
                    'INTERSECT': layer_intersecoes,
                    'METHOD': 0  # Método de seleção: criar nova seleção
                })

                if remover_feicoes_selecionadas(layer_vertices):
                    print("Feições coincidentes removidas com sucesso.")

                #remover elementos que sobrepoem linhas ou bordas de poligonos
                for layer_delete_aux in list_layer_aux:
                    
                    layer_aux = QgsProject.instance().mapLayersByName(layer_delete_aux)
                    
                    if not layer_aux:
                        print("A camada "+layer_delete_aux+" não foi encontrada.")
                    
                    else:
                        # Pega a primeira camada da lista
                        layer_aux = layer_aux[0]
                        if layer_aux.geometryType() == QgsWkbTypes.PolygonGeometry:
                            
                            # Transformar a camada de polígono em linha e armazenar como camada temporária
                            result = processing.run("native:polygonstolines", {
                                'INPUT': layer_aux,
                                'OUTPUT': 'memory:'  # Usar camada de memória
                            })
                            # Obtenha a nova camada de linha da saída do processamento
                            layer_aux = result['OUTPUT']

                            # Adicione a camada de linha ao projeto e exiba-a
                            #QgsProject.instance().addMapLayer(layer_moldura_linha)
                            #print("Camada de linha da moldura adicionada ao projeto.")
                        
                        if not layer_aux.geometryType() == QgsWkbTypes.LineGeometry:
                            print("A camada "+layer_delete_aux+" inválida para este processo.")

                        else:

                            # Execute a seleção por localização para selecionar os vértices que tocam, cruzam, se sobrepõem ou são iguais à linha da moldura
                            processing.run("native:selectbylocation", {
                                'INPUT': layer_vertices,
                                'PREDICATE': [0], #[0]corresponde ao operador "Igual a" (Equals)
                                'INTERSECT': layer_aux,
                                'METHOD': 0  # Método de seleção: criar nova seleção
                            })

                            if remover_feicoes_selecionadas(layer_vertices):
                                print("Feições coincidentes com camada "+layer_delete_aux+", removidas com sucesso.")
                                #remove do projeto a camada Vertices_Coincidentes
                                QgsProject.instance().removeMapLayer(layer_intersecoes.id())


        def verificar_toques_com_vertices(pt_vertices, check_layers_names):

            # Carregar a camada Pontos_Vertices
            points_layer = QgsProject.instance().mapLayersByName(pt_vertices)[0]

            # Verificar a existência da camada
            if not points_layer:
                print("A camada ", pt_vertices, " não foi encontrada.")
            else:
                # Adicionar campos à camada Pontos_Vertices para armazenar os resultados
                if points_layer.fields().indexOf('camadas_toque') == -1:
                    points_layer.dataProvider().addAttributes([
                        QgsField('camadas_toque', QVariant.String),  # Nomes das camadas tocadas
                        QgsField('quantidade_toques', QVariant.Int)  # Quantidade de toques
                    ])
                    points_layer.updateFields()

                # Criar camada temporária de buffer dos pontos
                buffer_layer = QgsVectorLayer(f"Polygon?crs={points_layer.crs().authid()}", "Buffers de Pontos", "memory")
                buffer_provider = buffer_layer.dataProvider()
                buffer_provider.addAttributes([QgsField("ID_Ponto", QVariant.Int)])
                buffer_layer.updateFields()

                # Criar buffers em torno de cada ponto
                for ponto_feature in points_layer.getFeatures():
                    ponto_geom = ponto_feature.geometry()
                    
                    if ponto_geom.isEmpty() or ponto_geom.type() != QgsWkbTypes.PointGeometry:
                        continue
                    
                    ponto = ponto_geom.asPoint()
                    tolerancia_graus = metros_para_graus(0.5, ponto.y())  # Tolerância de 0.5 metros convertida para graus
                    buffer_geom = ponto_geom.buffer(tolerancia_graus, segments=10)
                    
                    buffer_feature = QgsFeature()
                    buffer_feature.setGeometry(buffer_geom)
                    buffer_feature.setAttributes([ponto_feature['id']])
                    buffer_provider.addFeature(buffer_feature)

                buffer_layer.updateExtents()

                # Não adicionar a camada de buffers ao projeto, mas mantê-la para uso interno
                #QgsProject.instance().addMapLayer(buffer_layer)
                
                # Iniciar edição na camada de pontos
                points_layer.startEditing()

                print("Pontos Vertices toques:")

                # Iterar sobre cada camada para verificar os toques
                for layer_name in check_layers_names:
                    layer_aux = QgsProject.instance().mapLayersByName(layer_name)[0]
                    
                    if layer_aux:
                        # Se a camada for polígono, converter para uma camada temporária de linhas
                        if layer_aux.geometryType() == QgsWkbTypes.PolygonGeometry:
                            
                            # Transformar a camada de polígono em linha e armazenar como camada temporária
                            result = processing.run("native:polygonstolines", {
                                'INPUT': layer_aux,
                                'OUTPUT': 'memory:'  # Usar camada de memória
                            })
                            # Obtenha a nova camada de linha da saída do processamento
                            layer_to_check = result['OUTPUT']
                            
                        else:
                            layer_to_check = layer_aux  # Usar a própria camada se já for do tipo linha

                        # Selecionar buffers que tocam a camada atual
                        processing.run("native:selectbylocation", {
                            'INPUT': buffer_layer,
                            'PREDICATE': [0],  # Toca, cruza, sobrepõe ou é igual
                            'INTERSECT': layer_to_check,
                            'METHOD': 0  # Criar nova seleção
                        })

                        # Imprimir o nome da camada e o número de pontos selecionados
                        print(layer_name, len(buffer_layer.selectedFeatures()))
                        
                        # Atualizar atributos nos pontos que possuem buffers que tocam a camada atual
                        for buffer_feature in buffer_layer.selectedFeatures():
                            point_id = buffer_feature['ID_Ponto']
                            point_feature = points_layer.getFeature(point_id)

                            current_layers_toque = point_feature['camadas_toque'] if point_feature['camadas_toque'] else ''
                            current_quantity = point_feature['quantidade_toques'] if point_feature['quantidade_toques'] else 0

                            # Adicionar o nome da camada atual ao campo 'camadas_toque'
                            updated_layers_toque = ', '.join(
                                filter(None, [current_layers_toque, layer_name])  # Filtrar valores vazios
                            )
                            
                            # Atualizar os valores nos atributos
                            point_feature['camadas_toque'] = updated_layers_toque
                            point_feature['quantidade_toques'] = current_quantity + 1
                            points_layer.updateFeature(point_feature)

                        # Limpar seleção na camada de buffer
                        buffer_layer.removeSelection()
                        
                # Salvar edições na camada de pontos
                points_layer.commitChanges()
                print("A verificação de toques e a atualização dos atributos foram concluídas com sucesso!")

        # Função para adicionar vértices na camada de linhas com base em uma camada de pontos com buffer
        def adicionar_vertices_com_buffer(camada_linhas, camada_pontos, tolerancia_metros=0.5):
            # Iniciar a edição na camada de linhas
            if not camada_linhas.isEditable():
                camada_linhas.startEditing()

            # Criar uma nova camada temporária de polígonos para armazenar os buffers
            camada_buffer = QgsVectorLayer("Polygon?crs=" + camada_pontos.crs().authid(), "Buffers de Pontos", "memory")
            provider = camada_buffer.dataProvider()
            provider.addAttributes([QgsField("ID_Ponto", QVariant.Int)])
            camada_buffer.updateFields()
            
            # Lista para armazenar os IDs dos pontos a serem excluídos
            pontos_para_excluir = []

            # Iterar sobre cada ponto na camada de pontos
            for ponto_feature in camada_pontos.getFeatures():
                ponto_geom = ponto_feature.geometry()
                
                # Verificar se a geometria é um ponto
                if ponto_geom.isEmpty() or ponto_geom.type() != QgsWkbTypes.PointGeometry:
                    continue
                
                ponto = ponto_geom.asPoint()
                
                # Calcula a tolerância em graus para o buffer, baseado na latitude do ponto
                tolerancia_graus = metros_para_graus(tolerancia_metros, ponto.y())
                
                # Criar um buffer em torno do ponto com a tolerância convertida para graus
                buffer = ponto_geom.buffer(tolerancia_graus, segments=10)
                
                # Criar uma nova feição de buffer e adicioná-la à camada de buffers
                buffer_feature = QgsFeature()
                buffer_feature.setGeometry(buffer)
                buffer_feature.setAttributes([ponto_feature['id']])
                provider.addFeature(buffer_feature)
                
                # Iterar sobre cada feição na camada de linhas
                for linha_feature in camada_linhas.getFeatures():
                    linha_geom = linha_feature.geometry()
                    
                    # Verificar se a geometria da feição é do tipo linha
                    if linha_geom.type() != QgsWkbTypes.LineGeometry:
                        continue
                    
                    # Verifica se a linha toca o buffer do ponto
                    if linha_geom.intersects(buffer):
                        # Calcula a posição mais próxima na linha e obtém o ID do segmento
                        resultado = linha_geom.closestSegmentWithContext(ponto)
                        
                        if len(resultado) == 4:
                            distancia, _, vertice_id, f = resultado
                            
                            # Verifica se o ponto já existe na linha antes de adicionar
                            if distancia <= tolerancia_graus and not linha_geom.vertexAt(vertice_id) == QgsPointXY(ponto):
                                # Adicionar o ponto como novo vértice na geometria da linha
                                linha_geom.insertVertex(ponto.x(), ponto.y(), vertice_id)
                                camada_linhas.dataProvider().changeGeometryValues({linha_feature.id(): linha_geom})
                                print(f"Vértice adicionado em {ponto} na feição ID {linha_feature.id()}")
                                # Adiciona o ID do ponto à lista para exclusão
                                pontos_para_excluir.append(ponto_feature.id())
            
            # Salva as edições na camada de linhas
            camada_linhas.commitChanges()
            
            # Excluir os pontos processados da camada de pontos
            if pontos_para_excluir:
                camada_pontos.startEditing()
                camada_pontos.dataProvider().deleteFeatures(pontos_para_excluir)
                camada_pontos.commitChanges()
            
            # Não adicionar a camada de buffers ao projeto, mas mantê-la para uso interno
            # QgsProject.instance().addMapLayer(camada_buffer)

        def inserir_vertices_nas_camadas(pt_vertices, camadas_linhas_nomes):
            camada_pontos = QgsProject.instance().mapLayersByName(pt_vertices)[0]
            # Loop sobre cada camada de linha
            for camada_nome in camadas_linhas_nomes:
                camada_linhas = QgsProject.instance().mapLayersByName(camada_nome)
                if camada_linhas:
                    adicionar_vertices_com_buffer(camada_linhas[0], camada_pontos, tolerancia_metros=0.5)
                else:
                    print(f"Camada {camada_nome} não encontrada.")
            
            #renomeia
            camada_pontos.setName("Flags Vertices Delimitadores")
            # Atualizar a camada para refletir as alterações
            camada_pontos.triggerRepaint()

        #EXECUCAO

        gerar_vertices_coincidentes(list_gerar_vertices_coincidentes)
        add_progresso(progresso, 10)
        gerar_pontos_extremidades(layer_delimitadores_list, vertices_coincidentes, pt_vertices)
        add_progresso(progresso, 20)
        deletar_vertices_ok(pt_vertices, vertices_coincidentes, list_camadas_para_nao_ter_flags)
        add_progresso(progresso, 30)
        verificar_toques_com_vertices(pt_vertices, list_verificar_toques)
        add_progresso(progresso, 40)
        inserir_vertices_nas_camadas(pt_vertices, lista_camadas_inserir_vertices)
        add_progresso(progresso, 50)


        #HIDROGRAFIA

        # Nome das camadas
        linha_layer_name = 'delimitador_massa_dagua_l'
        ponto_layer_name = 'centroide_massa_dagua_p'
        list_elementos_toques_fluxo = [
            'elemnat_trecho_drenagem_l',
            'infra_trecho_duto_l',
            'infra_vala_l'
        ]

        def calcular_area(poligono_feat):
            # Calcule a área em graus quadrados
            area = poligono_feat.geometry().area()

            # Verificar se a geometria está em CRS geográfico
            if project_crs.isGeographic():
                # Calcule o centroide para obter a latitude
                centroid = poligono_feat.geometry().centroid()
                latitude = centroid.asPoint().y()
                # Calcule a área em metros quadrados
                area_m2 = area * (111320 * math.cos(math.radians(latitude))) ** 2
            else:
                area_m2 = area
            
            return area_m2

        # Obter as camadas
        linha_layer = QgsProject.instance().mapLayersByName(linha_layer_name)[0]
        ponto_layer = QgsProject.instance().mapLayersByName(ponto_layer_name)[0]

        # Verificar se as camadas foram encontradas
        if not linha_layer or not ponto_layer:
            print(f"Camada de {linha_layer_name} ou de {ponto_layer_name} não encontrada.")
        else:
            # Mesclar todas as linhas em uma única geometria
            geometria_mesclada = None
            for linha_feat in linha_layer.getFeatures():
                if geometria_mesclada:
                    geometria_mesclada = geometria_mesclada.combine(linha_feat.geometry())
                else:
                    geometria_mesclada = linha_feat.geometry()

            # Explodir a geometria mesclada em partes individuais
            partes_explodidas = geometria_mesclada.asGeometryCollection()

            # Criar uma camada temporária de polígono
            poligono_layer = QgsVectorLayer("Polygon?crs=" + linha_layer.crs().authid(), "Poligono_Massa_Dagua", "memory")
            poligono_layer.dataProvider().addAttributes([QgsField("id_linha", QVariant.Int)])
            poligono_layer.updateFields()

            # Lista para armazenar todas as linhas fechadas (QgsGeometry) para polygonize
            todas_linhas = []

            # Verificar fechamento de cada parte explodida e adicionar vértices, se necessário
            for parte in partes_explodidas:
                if parte.isMultipart():
                    linhas = parte.asMultiPolyline()
                else:
                    linhas = [parte.asPolyline()]

                for linha in linhas:
                    # Verificar se a linha está fechada
                    if linha[0] != linha[-1]:  # Se não estiver fechada
                        linha.append(linha[0])  # Fechar a linha adicionando o ponto inicial no final

                    # Adicionar a linha fechada como QgsGeometry na lista
                    todas_linhas.append(QgsGeometry.fromPolylineXY(linha))

            # Realizar a operação polygonize nas linhas fechadas
            poligono_geom = QgsGeometry.polygonize(todas_linhas)

            add_progresso(progresso, 60)

            # Verificar se `polygonize` criou múltiplos polígonos e adicionar à camada temporária
            poligono_parts = []
            if poligono_geom.isMultipart():
                poligono_parts = poligono_geom.asGeometryCollection()
            else:
                poligono_parts = [poligono_geom]

            for part in poligono_parts:
                poligono_feat = QgsFeature(poligono_layer.fields())
                poligono_feat.setGeometry(part)
                poligono_layer.dataProvider().addFeature(poligono_feat)

            # Atualizar a nova camada de polígono
            poligono_layer.updateExtents()
            #QgsProject.instance().addMapLayer(poligono_layer)

            # Criar uma nova camada de pontos para armazenar os flags dos centróides
            flags_centroids_layer = QgsVectorLayer("Point?crs=" + ponto_layer.crs().authid(), "flags_centroids_massa_dagua", "memory")
            flags_centroids_layer.dataProvider().addAttributes([ 
                QgsField("id", QVariant.Int),           # Nova coluna id
                QgsField("centroid_id", QVariant.Int),
                QgsField("massa_dagua_id", QVariant.Int),
                QgsField("descricao", QVariant.String),  # Nova coluna descrição
                QgsField("area_massa_dagua", QVariant.Double)     # Nova coluna para área em metros quadrados
            ])
            flags_centroids_layer.updateFields()

            # Índice espacial para os pontos e dicionário de pontos por massa d'água
            ponto_index = QgsSpatialIndex(ponto_layer.getFeatures())
            flags_data = []
            novo_centroid_id = 0  # Contador para os novos centróides
            flag_id_counter = 1    # Contador para IDs dos flags

            # Obter o sistema de referência do projeto
            project_crs = QgsProject.instance().crs()

            add_progresso(progresso, 70)

            # Iterar sobre cada polígono para verificar os pontos contidos
            for poligono_feat in poligono_layer.getFeatures():
                pontos_dentro = []
                for ponto_id in ponto_index.intersects(poligono_feat.geometry().boundingBox()):
                    ponto_feat = ponto_layer.getFeature(ponto_id)
                    if poligono_feat.geometry().contains(ponto_feat.geometry()):
                        pontos_dentro.append(ponto_feat)

                # Ordenar pontos por comprimento do nome (prioridade)
                pontos_dentro.sort(key=lambda x: len(x["nome"]) if x["nome"] else 0, reverse=True)

                # Criar feições na camada de flags para cada ponto dentro do polígono
                for ordem, ponto_feat in enumerate(pontos_dentro):
                    if ordem > 0:  # Ignorar ordem zero
                        flag_feat = QgsFeature(flags_centroids_layer.fields())
                        flag_feat.setGeometry(ponto_feat.geometry())
                        flag_feat.setAttributes([ 
                            flag_id_counter,          # id
                            ponto_feat.id(),          # centroid_id
                            poligono_feat.id(),       # massa_dagua_id
                            f"Centroides Excedentes, ordem: {ordem}",  # descrição
                            calcular_area(poligono_feat)    #area da massa dagua
                        ])
                        flags_data.append(flag_feat)
                        flag_id_counter += 1  # Incrementar o contador do ID do flag

            # Adicionar os flags na camada temporária e atualizar o projeto
            flags_centroids_layer.dataProvider().addFeatures(flags_data)
            flags_centroids_layer.updateExtents()

            add_progresso(progresso, 80)

            # Parte nova: criar centróides lineares para polígonos que não tocam pontos
            for poligono_feat in poligono_layer.getFeatures():
                pontos_dentro = []
                for ponto_id in ponto_index.intersects(poligono_feat.geometry().boundingBox()):
                    ponto_feat = ponto_layer.getFeature(ponto_id)
                    if poligono_feat.geometry().contains(ponto_feat.geometry()):
                        pontos_dentro.append(ponto_feat)

                # Verificar se há elementos tocando as camadas específicas
                toques = False

                for elementos_toques in list_elementos_toques_fluxo:
                    layer_toques_verificacao = QgsProject.instance().mapLayersByName(elementos_toques)

                    # Verificar se as camadas de drenagem, duto ou vala existem e se tocam o polígono
                    if layer_toques_verificacao and not toques:
                        for layer_toque_feat in layer_toques_verificacao[0].getFeatures():
                            if poligono_feat.geometry().intersects(layer_toque_feat.geometry()):
                                toques = True
                                break

                # Se não houver pontos dentro do polígono, calcular o centróide linear
                if not pontos_dentro:
                    # Calcular o centróide linear do polígono
                    centroid_linear = poligono_feat.geometry().centroid()

                    # Adicionar o ponto do centróide linear à camada flags_centroids_layer
                    novo_centroid_id += 1  # Incrementar o ID dos novos centróides
                    flag_feat = QgsFeature(flags_centroids_layer.fields())
                    flag_feat.setGeometry(centroid_linear)

                    # Definir a descrição com base no toque
                    if toques:
                        descricao = "Novo Centroide com fluxo"
                    else:
                        descricao = "Novo Centroide sem fluxo"

                    flag_feat.setAttributes([
                        flag_id_counter,          # id (ID gerado)
                        novo_centroid_id,        # centroid_id (ID gerado)
                        poligono_feat.id(),      # massa_dagua_id
                        descricao,                # descrição
                        calcular_area(poligono_feat) #area da massa dagua
                    ])

                    # Adicionar a nova feição ao flags_centroids_layer
                    flags_centroids_layer.dataProvider().addFeature(flag_feat)

                    # Incrementar contador de ID
                    flag_id_counter += 1

            # Adicionar a camada de flags ao projeto
            QgsProject.instance().addMapLayer(flags_centroids_layer)

            print("Processo concluído.")

            add_progresso(progresso, 100)



        results = {}

        return results


    def name(self):
        return 'aux_veg_1_cobter'

    def displayName(self):
        return 'Aux Veg 1 - Cobertura Terrestre'

    def group(self):
        return 'Aux Veg'

    def groupId(self):
        return 'aux_veg'

    def createInstance(self):
        return AuxVeg1()

    def shortHelpString(self):
        return QCoreApplication.translate(
            "AuxVeg1", 
            "Este script utiliza algoritmos para gerar pontos de "
            "interseção onde não existem, especificamente entre as camadas linhas "
            "que tocam nas extreminadas dos delimitadores e não adicionando vertices "
            " a camada moldura. Este processo é essencial para garantir a "
            "precisão topológica das interseções, permitindo uma análise espacial mais "
            "coerente e a correção de inconsistências nos dados geoespaciais.\n\n"
            "Autoria de desenvolvimento de script Python: 2º Sgt Marcos Batista do 3º CGEO."
    )


# This script is part of the tools developed by Marcos Batista, Python developer specializing in cartography and GIS.
