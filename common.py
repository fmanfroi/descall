import logging
import urllib3

# configure logging once for the entire project
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# suppress insecure SSL warnings globally
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
