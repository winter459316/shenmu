"""One HDMI+compute concurrency test, followed by verified stable rollback."""
import hashlib,json,sys
from pathlib import Path
import test_sgm_v4_transaction as transaction
ROOT=Path(__file__).resolve().parent
proof=json.loads((ROOT/'hdmi_hardware_verified.json').read_text())
assert proof['timing_passed'] and proof['cdc_review_passed'] and proof['key_synchronizers_verified']
assert hashlib.sha256((ROOT/'hdmi_v1.bit.bin').read_bytes()).hexdigest()==proof['bin_sha256']
transaction.CANDIDATE=proof['bin_sha256']
transaction.CANDIDATE_FILE='hdmi_v1.bit.bin'
transaction.HDMI_TEST=True
sys.argv=['test_hdmi_transaction.py','--full-pipeline']
transaction.main()
