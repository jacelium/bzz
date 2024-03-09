# Config
deny_list = None # List of names. If set, these users will not trigger a response
allow_list = ['jacel'] # List of names. If set, these are the only users who will trigger a response
scaler = 1 # All triggers will be scaled by this amount. e.g. to half all triggers, set this to 0.5 or 1/2
poll_interval = 10 # The minimum space between shocks. Also the interval for polling for replies.
verbose = False # Extra output

# If True, only direct responses to the original post will be counted. If False, all children are considered
strict = False

# These will be posted if target_id is unset

post_body = "This is the post that will be made on your behalf. :boost_ok:"
post_cw = "Enter some valid CWs and keywords here!"
post_privacy = "unlisted" # direct, private unlisted public

# File paths - files are used for storing some mostly ephemeral stuff and also config/logs
# TODO: Should use actual Python logging but this is quick-and-dirty
logfilepath = './log.txt'
lastfile = './last.txt'
credsfile = './creds.json'
targetfile = './target.txt'

#############################################################
# Creds file should be a JSON file in this format:
#{
#  "mast_username": "mastodon username",
#  "mast_password": "mastodon password",
#  "mast_appname": "The Mastodon app name",
#  "mast_baseurl": "Your Mastodon instance's base URL",
#  "shock_key": "The key from your share link (looks like a guid)",
#  "shock_username": "Your pishock username",
#  "shock_sharecode": "Your pishock sharecode",
#  "shock_appname": "The app name that will appear in Pishock logs"
#}
#############################################################

# Config done

import json, os, sys, re, time, datetime
from pishockpy import PishockAPI
from mastodon import Mastodon

# TODO: Should use an actual config library but quick-and-dirty
creds = {}

with open(credsfile, 'r') as config_file:
  creds = json.loads(config_file.read())

clientpath = f'./{creds["mast_appname"]}_client.secret'
userpath = f'./{creds["mast_appname"]}_user.secret'

if not os.path.isfile(clientpath):
  Mastodon.create_app(creds['mast_appname'], api_base_url=creds["mast_baseurl"], to_file=clientpath)

m = Mastodon(client_id=clientpath)

if not os.path.isfile(userpath):
  m.log_in(creds["mast_username"], creds["mast_password"], to_file=userpath)

m = Mastodon(access_token=userpath)

print(f'\nStarting {creds["mast_appname"]}')
print(f'Scaler is {scaler}')

if deny_list:
  print(f'Deny list is {deny_list}')
if allow_list:
  print(f'Allow list is {allow_list}')

# If we're triggering a newpost, delete any old targetfile

target_id = None

try:
  if len(sys.argv) > 1 and sys.argv[1] == 'newpost':
    try:
      os.remove(targetfile)
    except FileNotFoundError:
      pass

  with open(targetfile, 'a'):
    pass
  with open(targetfile, 'r') as file:
    target_id = int(file.readlines()[0])
    print(f'Using existing post id: {target_id}')
except:
  pass

if target_id is None:
  # Clear the lastseen file and post a start post
  try:
    os.remove(lastfile)
  except FileNotFoundError:
    pass

  line_length = 70
  body_len = len(post_body)
  body = [ post_body[i:i+line_length] for i in range(0, body_len, line_length) ]
  separator = '\n'

  print(f'\nWill post new {post_privacy.upper()} status in { "STRICT" if strict else "NON-STRICT"} mode:\n')
  print('-----------------------------------------------------------')
  print(f' CW: {post_cw}\n\n {separator.join(body)}')
  print('\n-----------------------------------------------------------\n')

  input_id = input('Please enter an existing status ID to listen to, or just hit enter\nto post and listen to the above status. ctrl-C cancels.\n> ')

  if input_id == '':
    new_post = m.status_post(post_body, visibility=post_privacy, spoiler_text=post_cw)
    target_id = new_post['id']
    print(f'Post made. View it at {new_post["url"]}')
  else:
    print(f'Using provided status ID: {input_id}')
    target_id = int(input_id)

  with open(targetfile, 'a'):
    pass
  with open(targetfile, 'w') as file:
    file.writelines([f'{target_id}'])

# Ensure lastfile exists
with open(lastfile, 'a'):
  pass

last_action_id = None
try:
  with open(lastfile, 'r') as file:
    last_action_id = int(file.readlines()[0])
except:
  pass

def find_index(predicate, l):
  for i,e in enumerate(l):
    if predicate(e): return i
  return None

def doit(parse, act, last_action_id):
  queue = []

  while True:
    if verbose: print(f'Fetching notifications. Last seen is {last_action_id}')
    # TODO: This is kind of brute-forcey. Can we filter by last seen time?
    notifications = m.status_context(target_id)['descendants']

    if strict:
      target_replies = list(filter(lambda x: x['in_reply_to_id'] == target_id, notifications))
    else:
      target_replies = notifications

    if target_replies == []:
      time.sleep(poll_interval)
      continue

    target_replies.sort(key=lambda x: x['created_at'])

    subset = []

    if last_action_id is None:
      subset = target_replies
    else:
      last_actioned = find_index(lambda x: x['id'] == last_action_id, target_replies)
      subset = target_replies[last_actioned+1:]

    subset = list(subset)

    if len(subset) == 0:
      if verbose: print('Nothing to process.')

    for item in list(subset):
      result = parse(item)
      if result:
        queue.append(result)

      last_action_id = item['id']

      with open(lastfile, 'w') as file:
        if verbose: print(f'Last seen is now {last_action_id}')
        file.writelines([f'{last_action_id}'])

    try:
      act(queue.pop(0))
    except:
      if verbose: print('Nothing to send')

    time.sleep(poll_interval)

# We need to provide two methods. The first, Parse, takes a post and extracts some information from it.
# If we're skipping, return False instead.

def parse(item):
  post = item['content']

  matches = re.search('b[z]{1,10}', post)

  if matches:
    count = len(matches.group(0))-1
    intensity = count * 10
    if deny_list is not None and item['account']['username'].lower() in deny_list:
       print(f'Skipping {intensity} from {item["account"]["username"]}, sent {item["created_at"].isoformat()} [denylist]')
    elif allow_list is not None and item['account']['username'].lower() not in allow_list:
       print(f'Skipping {intensity} from {item["account"]["username"]}, sent {item["created_at"].isoformat()} [allowlist]')
    else:
       print(f'Pushing {intensity} from {item["account"]["username"]}, sent {item["created_at"].isoformat()}')
       return([intensity, item['account']['username'], item['created_at']])
  return False

# The second is what to actually do with what Parse produces.

# we need a Pishock instance for this handler
ps = PishockAPI(creds['shock_key'], creds['shock_username'], creds['shock_sharecode'], creds['shock_appname'])

def act(item):
    intensity, user, sent = item

    with open(logfilepath, 'a') as logfile:
      logfile.write(f'{target_id},{sent.isoformat()},{datetime.datetime.now().isoformat()},{intensity},{user}\n')

    print(f'Sending {intensity} ({intensity/100}) on behalf of {user}')

    if scaler != 1:
      print(f'Scaled shock: {(intensity/100) * scaler * 100}')

    ps.shock((intensity / 100) * scaler, 1)

# Start monitoring. Pass our two methods to the harness, along with our saved last_action_id if we have one.

doit(parse, act, last_action_id)
