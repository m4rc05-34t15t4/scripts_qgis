# Este script faz a compressão de imagens
from qgis.PyQt.QtWidgets import QFileDialog
from qgis.core import (QgsProcessing, 
                       QgsProcessingAlgorithm, 
                       QgsProcessingParameterRasterLayer, 
                       QgsProcessingParameterFolderDestination, 
                       QgsProcessingException, 
                       QgsProcessingOutputString,
                       QgsProcessingContext)
import os
import subprocess
from osgeo import gdal

class CompressRasterImagesYCbCrAlgorithm(QgsProcessingAlgorithm):
    INPUT_RASTERS = 'INPUT_RASTERS'
    OUTPUT_DIR = 'OUTPUT_DIR'
    OUTPUT_MSG = 'OUTPUT_MSG'

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterRasterLayer(
                self.INPUT_RASTERS,
                'Select raster images',
                [QgsProcessing.TypeRaster]
            )
        )

        self.addParameter(
            QgsProcessingParameterFolderDestination(
                self.OUTPUT_DIR,
                'Output directory'
            )
        )

        self.addOutput(
            QgsProcessingOutputString(
                self.OUTPUT_MSG,
                'Output message'
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        input_rasters = self.parameterAsLayerList(parameters, self.INPUT_RASTERS, context)
        output_dir = self.parameterAsString(parameters, self.OUTPUT_DIR, context)

        if not input_rasters or not output_dir:
            raise QgsProcessingException("Input files or output directory is not specified.")
        
        compression_results = []

        for raster in input_rasters:
            input_file = raster.source()
            output_file = os.path.join(output_dir, os.path.splitext(os.path.basename(input_file))[0] + '_compressed.tif')
            
            feedback.pushInfo(f"Compressing {input_file} to {output_file}")

            # Execute GDAL Translate Command for Compression
            gdal_translate_command = [
                'gdal_translate',
                '-co', 'COMPRESS=JPEG',
                '-co', 'PHOTOMETRIC=YCBCR',
                '-co', 'TILED=YES',
                input_file,
                output_file
            ]
            
            try:
                result = subprocess.run(gdal_translate_command, capture_output=True, text=True, check=True)
                feedback.pushInfo(result.stdout)
                feedback.pushInfo(f"Compressed {input_file} to {output_file}")

                # Calculate Compression Ratio
                original_size = os.path.getsize(input_file)
                compressed_size = os.path.getsize(output_file)
                compression_ratio = 100 * (1 - (compressed_size / original_size))
                compression_results.append(f"{input_file} compressed by {compression_ratio:.2f}%")

            except subprocess.CalledProcessError as e:
                feedback.reportError(f"Error executing gdal_translate: {e.stderr}")
                raise QgsProcessingException(f"Error executing gdal_translate: {e.stderr}")

        feedback.pushInfo("\n".join(compression_results))
        
        return {self.OUTPUT_MSG: "Compression complete. Check the log for compression ratios."}

    def name(self):
        return 'compress_raster_images_ycbcr'

    def displayName(self):
        return 'Compress Raster Images to YCbCr Format'

    def group(self):
        return 'Raster Processing'

    def groupId(self):
        return 'rasterprocessing'

    def createInstance(self):
        return CompressRasterImagesYCbCrAlgorithm()

    def shortHelpString(self):
        return ("Compress Raster Images to YCbCr Format\n"
                "This tool can be used to compress multiple raster images using the YCbCr compression method. "
                "The output includes:\n"
                "1 - Compressed raster images in YCbCr format.\n"
                "2 - Significant reduction in file size while maintaining image quality.\n"
                "Author: Thiago Arruda - GIS Specialist")
