"""Fail closed until a real Cloud Run URL and all team members are present."""
import json
import re
from pathlib import Path

content = json.loads((Path(__file__).resolve().parent / 'submission.json').read_text(encoding='utf-8'))
assert content.get('path') == 'research', 'path must equal research'
assert isinstance(content.get('authors'),list) and content['authors'], 'authors must include all team members'
assert isinstance(content.get('deploy_url'),str) and re.fullmatch(r'https://[^\s]+\.run\.app/?',content['deploy_url']), 'Deploy to Cloud Run and update deploy_url with the real https://...run.app URL'
print('Submission structure and deploy URL format validated. Test actual reachability separately.')
