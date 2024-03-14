import logging
import threading
import json, os, time
from mastodon import Mastodon
from .config import Config
from .util import find_index

#############################################################
# Mastodon Creds file should be a JSON file in this format:
#{
#  "mast_username": "mastodon username",
#  "mast_password": "mastodon password",
#  "mast_appname": "The Mastodon app name",
#  "mast_baseurl": "Your Mastodon instance's base URL"
#}
#############################################################

class Bzz:
  def __init__(self, parse_function, act_function, **kwargs):

    # Bootstrap our config file
    self.config_file_path = kwargs.get('config_file', './bzz.conf')
    try:
      self.c = Config.from_file(self.config_file_path)
    except ValueError as e:
      print(f'Malformed configuration: {e}')
      raise
    except FileNotFoundError as e:
      print(f'Config file does not exist. Creating a defaulted config under {self.config_file_path}. Edit this file and re-run!')
      self.c = Config()
      self.c.save(self.config_file_path)
      exit()

    self.parse_function = parse_function
    self.act_function = act_function
    self.stats_function = kwargs.get('stats_function', None)
    if self.c.close_stats and self.stats_function is None:
      print('*** Warning: `close_stats` is true and no stats function is set ***')

    self.empty_function = kwargs.get('empty_function', None)

    self.log = logging.getLogger(__name__)

    self.queue = []
    self.read_thread = None
    self.target_id = None

    # Setup Mastodon client
    # TODO: Should use an actual config library but quick-and-dirty
    creds = {}

    with open(self.c.credsfilepath, 'r') as creds_file:
      creds = json.loads(creds_file.read())

    clientpath = f'./{creds["mast_appname"]}_client.secret'
    userpath = f'./{creds["mast_appname"]}_user.secret'

    if not os.path.isfile(userpath):
      if not os.path.isfile(clientpath):
        Mastodon.create_app(creds['mast_appname'], api_base_url=creds["mast_baseurl"], to_file=clientpath)

      m = Mastodon(client_id=clientpath)
      m.log_in(creds["mast_username"], creds["mast_password"], to_file=userpath)

    self.app_name = creds["mast_appname"]
    self.m = Mastodon(access_token=userpath)

  def create_post(self):
    try:
      os.remove(self.c.targetfilepath)
    except FileNotFoundError:
      pass
    self.attach_to_post(existing=False)

  def attach_to_post(self, existing=True):
    with open(self.c.targetfilepath, 'a') as file:
      pass
    with open(self.c.targetfilepath, 'r') as file:
      try:
        self.target_id = int(file.readlines()[0])
        print(f'Using existing post id: {self.target_id}')
      except IndexError:
        if existing: print(f'Couldn\'t read post ID from file')

    if self.target_id is None:
      # Clear the lastseen file and post a start post
      try:
        os.remove(self.c.lastfilepath)
      except FileNotFoundError:
        pass

      line_length = 70
      body_len = len(self.c.post_body)
      body = [ self.c.post_body[i:i+line_length] for i in range(0, body_len, line_length) ]
      separator = '\n'

      print(f'\nWill post new {self.c.post_privacy.upper()} status in { "STRICT" if self.c.strict else "NON-STRICT"} mode:\n')
      print('-----------------------------------------------------------')
      print(f' CW: {self.c.post_cw}\n\n {separator.join(body)}')
      print('\n-----------------------------------------------------------\n')

      input_id = input('Please enter an existing status ID to listen to, or just hit enter\nto post and listen to the above status. ctrl-C cancels.\n> ')

      if input_id == '':
        new_post = self.m.status_post(self.c.post_body, visibility=self.c.post_privacy, spoiler_text=self.c.post_cw)
        self.target_id = new_post['id']
        print(f'Post made. View it at {new_post["url"]}')
      else:
        print(f'Using provided status ID: {input_id}')
        self.target_id = int(input_id)

      with open(self.c.targetfilepath, 'a') as file:
        pass
      with open(self.c.targetfilepath, 'w+') as file:
        file.writelines([f'{self.target_id}'])

  def close_post(self):
    self.attach_to_post()
    # If we're closing a post, do so and exit
    if not self.target_id:
      print('No current target set; can\'t close off post')
      exit()

    stats_marker = ' and generating stats' if self.c.close_stats and self.stats_function is not None else ''
    print(f'Closing post {self.target_id} by appending {self.c.closed_marker} to CW{stats_marker}')

    post = self.m.status(self.target_id)
    existing_cw = post['spoiler_text']
    cw_text = f'{existing_cw} {self.c.closed_marker}' if self.c.closed_marker not in existing_cw else existing_cw

    stats_text = ''
    if self.c.close_stats and self.stats_function is not None:
      stats_text = self.stats_function(self.target_id, self.c)

    self.m.status_update(self.target_id, f'{self.c.post_body}{stats_text}', spoiler_text=cw_text)
    exit()

  def run(self):
    print(f'\nStarting {self.app_name}')

    if self.c.deny_list:
      print(f'Deny list is {self.c.deny_list}')
    if self.c.allow_list:
      print(f'Allow list is {self.c.allow_list}')

    self.queue = []

    # Ensure lastfile exists
    with open(self.c.lastfilepath, 'a'):
      pass

    self.last_action_id = None
    try:
      with open(self.c.lastfilepath, 'r') as file:
        self.last_action_id = int(file.readlines()[0])
    except:
      pass

    def read_method(queue):
      while True:
        if self.c.verbose: print(f'Fetching responses. Last seen is {self.last_action_id}')
        # TODO: This is kind of brute-forcey. Can we filter by last seen time?
        responses = self.m.status_context(self.target_id)['descendants']

        if self.c.strict:
          target_replies = list(filter(lambda x: x['in_reply_to_id'] == self.target_id, responses))
        else:
          target_replies = responses

        if target_replies == []:
          time.sleep(self.c.parse_interval)
          continue

        target_replies.sort(key=lambda x: x['created_at'])

        subset = []

        if self.last_action_id is None:
          subset = target_replies
        else:
          last_actioned = find_index(lambda x: x['id'] == self.last_action_id, target_replies)
          subset = target_replies[last_actioned+1:]

        subset = list(subset)

        if len(subset) == 0:
          if self.c.verbose: print('Nothing to process.')


        for item in list(subset):
          result = self.parse_function(item, self.c)
          if result:
            self.queue.append(result)

          self.last_action_id = item['id']

          with open(self.c.lastfilepath, 'w') as file:
            if self.c.verbose: print(f'Last seen is now {self.last_action_id}')
            file.writelines([f'{self.last_action_id}'])
        time.sleep(self.c.parse_interval)

    print('Starting read thread...')
    self.read_thread = threading.Thread(target=read_method, args=(self.queue,))
    self.read_thread.start()

    while True:
      try:
        result = self.act_function(self.queue[0], self.target_id, self.c)
        if result != False:
          self.queue.pop(0)
      except IndexError as e:
        if self.c.verbose: print('Nothing to send')

        if self.empty_function is not None:
          result = self.empty_function(self.queue) # Manipulate the queue in some way...
          if result == True:
            continue # ...and immediately process it we returned True.
      except Exception as e:
        print(e)

      time.sleep(self.c.act_interval)
