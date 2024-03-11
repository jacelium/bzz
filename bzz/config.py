import json
from dataclasses import dataclass, asdict

class AllowedValue:
  def __init__(self, valid_values):
    self.valid = valid_values

  def run(self, value, field_name):
    if value not in self.valid:
      raise ValueError(f'{field_name}: Value \'{value}\' must be one of {self.valid}')

@dataclass
class Config:
  """ default config. Any of these can be overwritten """

  allowed_values = {
    'post_privacy': AllowedValue(['direct', 'private', 'unlisted', 'public'])
  }

  def __post_init__(self):
    for field, test in self.allowed_values.items():
      if field in self.__dict__:
        test.run(self.__dict__[field], field)

  name: str = 'Default' # The name for this app

  deny_list: list = None # List of account names. If set, these users will not trigger a response
  allow_list: list = None # List of account names. If set, these are the only users who will trigger a response

  parse_interval: int = 10 # The time between attempts to poll the target post
  act_interval: int = 5 # The minimum space between triggers
  verbose: bool = False # Replace with loglevels

  closed_marker: str = '[FINISHED]' # Appended to a post's CW when closing it
  close_stats: bool = False # Whether to generate stats on close

  # If True, only direct responses to the original post will be counted. If False, all children are considered
  strict: bool = False

  post_body: str = """ """
  post_cw: str = 'Your post CWs go here'
  post_privacy: str = 'unlisted'

  # File paths - files are used for storing some mostly ephemeral stuff and also config/logs
  # TODO: Should use actual Python logging but this is quick-and-dirty
  logfilepath: str = './log.txt' # logfile
  lastfilepath: str = './last.txt' # last processed file
  credsfilepath: str = './creds.json' # credentials file
  targetfilepath: str = './target.txt' # target_id for current post

  knownfilepath: str = './known.txt' # stores previously seen names for stats  

  def _load_from_file(filename):
    json_values = {}
    with open(filename, 'r') as config_file:
      json_values = json.loads(config_file.read())
    return json_values

  def from_file(filename):
    values = Config._load_from_file(filename)
    return Config(**values)

  def _get_as_json(self):
    return json.dumps(asdict(self))

  def save(self, filename):
    try:
      with open(filename, 'w') as config_file:
        json.dump(asdict(self), config_file, indent=2)
    except Exception as e:
      print(f'unable to save {filename}')
