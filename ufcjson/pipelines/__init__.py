from .image import UfcDefaultPhotoPipeline, ImagesDownloadPipeline
from .country_flag import UfcCountryCodePipeline
from .translate import TranslatorPipeline
from .export_json import JsonWriterPipeline
from .export_db import SqliteDbPipeline
from .rss_export import UfcRssMakerPipeline

__all__ = [
    'UfcDefaultPhotoPipeline',
    'ImagesDownloadPipeline',
    'UfcCountryCodePipeline',
    'TranslatorPipeline',
    'JsonWriterPipeline',
    'SqliteDbPipeline',
    'UfcRssMakerPipeline',
]
