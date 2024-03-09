# Config
deny_list = None # List of account names. If set, these users will not trigger a response
allow_list = ['jacel@m.prettyshiny.org'] # List of account names. If set, these are the only users who will trigger a response
scaler = 1 # All triggers will be scaled by this amount. e.g. to half all triggers, set this to 0.5 or 1/2
poll_interval = 10 # The minimum space between shocks. Also the interval for polling for replies.
verbose = False # Extra output
closed_marker = '[FINISHED]' # Appended to a post's CW when closing it
close_stats = True # Whether to generate stats on close

# If True, only direct responses to the original post will be counted. If False, all children are considered
strict = False

# These will be posted if target_id is unset

post_body = "This is the post that will be made on your behalf. :boost_ok:"
post_cw = "Enter some valid CWs and keywords here!"
post_privacy = "unlisted" # direct, private unlisted public

# File paths - files are used for storing some mostly ephemeral stuff and also config/logs
# TODO: Should use actual Python logging but this is quick-and-dirty
logfilepath = './log.txt' # logfile
lastfilepath = './last.txt' # last processed file
credsfilepath = './creds.json' # credentials file
targetfilepath = './target.txt' # target_id for current post

knownfilepath = './known.txt' # stores previously seen names for stats

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

with open(credsfilepath, 'r') as creds_file:
  creds = json.loads(creds_file.read())

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

def generate_stats(post_id):
  known = []
  updated = []

  with open(knownfilepath, 'w+') as knownfile:
    known = set(knownfile.readlines())
    updated = known.copy()

  logs = []
  with open(logfilepath, 'r') as logfile:
    logs = logfile.readlines()
  logs = list(filter(lambda x: x.startswith(str(post_id)), logs))

  count = len(logs)
  if count == 0:
    return '\n\nNo triggers received! :('

  newusers = set()
  max = 0
  total = 0
  biggest = set()

  for log in logs:
    fields = log.split(',')
    intensity, name = int(fields[3]), fields[4]
    if name not in known:
      updated.add(name)
    if intensity >= max:
      max = intensity
      biggest.add(name.strip())
    total += intensity

  def format_userlist(list, sep=', @', last_sep=' and @'):
    output = sep.join(list)
    if sep in output:
      output = last_sep.join(output.rsplit(sep, 1))
    return output

  biggest = format_userlist(biggest)
  new_names = updated - known
  #new_names_string = format_userlist(new_names)
  with open(knownfilepath, 'w') as knownfile:
    knownfile.writelines(updated)

  return f'\n\nMax was {max} (from @{biggest})\nAverage was {total/count} across {count} triggers\n{len(new_names)} new users'

arg = sys.argv[1] if len(sys.argv) > 1 else ''

# If we're triggering a newpost, delete any old targetfile

target_id = None

if arg == 'newpost':
  try:
    os.remove(targetfilepath)
  except FileNotFoundError:
    pass

with open(targetfilepath, 'a') as file:
  pass
with open(targetfilepath, 'r') as file:
  try:
    target_id = int(file.readlines()[0])
    print(f'Using existing post id: {target_id}')
  except IndexError:
    if arg != 'newpost': print(f'Couldn\'t read post ID from file')

# If we're closing a post, do so and exit
if arg == 'closepost':
  if not target_id:
    print('No current target set; can\'t close off post')
    exit()

  stats_marker = ' and generating stats' if close_stats else ''
  print(f'Closing post {target_id} by appending {closed_marker} to CW{stats_marker}')

  post = m.status(target_id)
  existing_cw = post['spoiler_text']
  cw_text = f'{existing_cw} {closed_marker}' if closed_marker not in existing_cw else existing_cw
  stats_text = ''

  if close_stats:
    stats_text = generate_stats(target_id)

  m.status_update(target_id, f'{post_body}{stats_text}', spoiler_text=cw_text)
  exit()

if target_id is None:
  # Clear the lastseen file and post a start post
  try:
    os.remove(lastfilepath)
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

  with open(targetfilepath, 'a') as file:
    pass
  with open(targetfilepath, 'w+') as file:
    print(f'writing {target_id} to file')
    file.writelines([f'{target_id}'])

# Ensure lastfile exists
with open(lastfilepath, 'a'):
  pass

last_action_id = None
try:
  with open(lastfilepath, 'r') as file:
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

      with open(lastfilepath, 'w') as file:
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
    acct = item['account']['acct']
    if deny_list is not None and acct.lower() in deny_list:
       print(f'Skipping {intensity} from {acct}, sent {item["created_at"].isoformat()} [denylist]')
    elif allow_list is not None and acct.lower() not in allow_list:
       print(f'Skipping {intensity} from {acct}, sent {item["created_at"].isoformat()} [allowlist]')
    else:
       print(f'Pushing {intensity} from {acct}, sent {item["created_at"].isoformat()}')
       return([intensity, acct, item['created_at']])
  return False

# The second is what to actually do with what Parse produces.

# we need a Pishock instance for this handler
ps = PishockAPI(creds['shock_key'], creds['shock_username'], creds['shock_sharecode'], creds['shock_appname'])

def act(item):
    intensity, user, sent = item

    with open(logfilepath, 'a+') as logfile:
      logfile.write(f'{target_id},{sent.isoformat()},{datetime.datetime.now().isoformat()},{intensity},{user}\n')

    print(f'Sending {intensity} ({intensity/100}) on behalf of {user}')

    if scaler != 1:
      print(f'Scaled shock: {(intensity/100) * scaler * 100}')

    ps.shock((intensity / 100) * scaler, 1)

# Start monitoring. Pass our two methods to the harness, along with our saved last_action_id if we have one.

doit(parse, act, last_action_id)
