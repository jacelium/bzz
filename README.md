# Bzz

Hooks up a Mastodon post to any API that can receive calls from Python.

Just look at the config section and the parse/act methods. I've tried to make them pretty obvious!

The user is expected to provide their own `parse` and `act` methods, and optionally an `empty` method for when the queue has nothing to process and a `generate_stats` method for adding extra data to a post when it's closed.

# Quick start with the sample app
Requirements:
- Python 3
- `venv`
- A Pishock
- A Mastodon account

Clone the repo, then in the root folder run:
```bash
python3 -m venv venv
source venv/bin/activate
pip3 install -r requirements.txt
```

Three configuration files are needed for the sample app. These files are .gitignored to prevent you accidentally checking them in. The first two must exist before the application will run.

- Credentials for Mastodon, default location `creds.json`, format as follows:
  ```
  {
    "mast_appname": "The name of your app, i.e. Bzz",
    "mast_username": "Your mastodon username",
    "mast_password": "your Mastodon password",
    "mast_baseurl": "The base URL for your instance, i.e. https://dragon.style/"
  }

  ```
- Credentials for Pishock, default location `shock_creds.json`, format as follows:
  ```
  {
    "shock_key": "An API key generated from the 'account' page on pishock.com",
    "shock_username": "your username",
    "shock_sharecode": "a sharecode generated from https://pishock.com/#/control",
    "shock_appname": "The name to display in logs (i.e. Bzz)"
  }
  ```
- Bzz config. The sample app uses `config.json` and if you run without creating it, it'll scaffold you a new one.

# Usage
Just run `python3 app.py` for the example app. This shows the following usage through the `create_post()`, `attach_to_post()` and `close_post()` methods:
- `python3 app.py`: attaches to an existing linked post. If none is found, offers to create one based on config and attach to that, or accepts a defined post ID.
- `python3 app.py newpost`: clears context for current post and creates a new one as above. WARNING: if you run this and then ctrl-c before creating the new post, the old post's context is still deleted.
- `python3 app.py closepost`: attempts to 'close' the current post - appends a marker to its CWs and optionally generates statistics.

# General structure
The application has an internal queue, and the main two user-provided methods interact with it. It has an idea of what post it's 'attached' to, by ID.

- `parse_function` reads the body of a Mastodon post on a cadence set by the config variable `parse_interval` and extracts whatever you want from it. It then drops it onto the queue.
  - Receives the following arguments:
    - The current item (see [here](https://mastodonpy.readthedocs.io/en/stable/02_return_values.html#toot-status-dicts) for the format of this object)
    - The `config` object for Bzz.
  - Returns:
    - The item to be appended to the queue
  - You can read anything you like from the post and then dump it into the queue.
  - You can also update global state from here to do other things - how often has this user replied, current intensity of output, whatever.
  - In the basic application, this method matches `[bB][z]{1,10}` against the post and counts the length of the match to get a value from 1-10. It also captures the current user and the time of the post.
  - What gets pushed to the queue is `[intensity, acct, post_time]`
- `act_function` receives one item from the queue on a cadence set by the config variable `act_interval` and performs some actions. 
  - Receives the following arguments:
    - The current item (The format of this will match whatever you returned from `parse`)
    - The ID of the current listen-target
    - The `config` object for Bzz.
  - Returns:
    - Nothing
  - What actions? Whatever you like! Set an intensity, set a target and smoothly ramp towards it, send outputs to two or more targets, who knows!
  - The basic application receives `[intensity, acct, post_time]`, and simply triggers a shock of the appropriate intensity by calling `ps.shock(intensity 1)`. (It also does some global scaling to allow for comfort levels and some logging for statistical purposes but that's not part of the actual 'make stuff happen')

There are two optional methods that can also be provided:
- `empty_function` is called on the `act` cadence when the queue is empty. It receives the queue and is expected to manipulate it in some way.
  - Receives the following arguments:
    - The queue (a simple Python list)
  - Returns:
    - `True`: process the queue again immediately
    - Anything else: Fall back to the usual queue processing behaviour
  - You can use it to push things to the queue, or to ramp down your steady-state output when there's no input, or any of a number of things
  - Return `True` to force immediate processing of the new item. Return `False` to let it fall through to the normal `act` cadence.
- `stats_function` is called upon closing a post. It can do whatever you like with anything you've generated during the lifetime of the program.
  - Receives the following arguments:
    - The ID of the current listen-target
    - The `config` object for Bzz.
  - In the basic app it reads the logfile that gets written to as part of `act`, parses the log lines and produces the following format:
    ```
    <Original post body here>

    Closed at 18:30, 15 March

    - Max intensity was 60% (from @some_user and @some_other_user)
    - Average intensity was ~43% across 19 triggers
    - 3 new visitors this time! (Hi @some_user, @some_other_user and @a_third_user!
    ```

# TODO
- Proper configuration!
- ~Proper encapsulation! (Objectify that sucka)~
- Better state handling!
  - Provide a state dict that can be configured up-front and then is passed to `parse` and `act` so we can store stuff in it rather than relying on global state. This allows us to save it to the filesystem and maintain it across runs.
- ~Threaded poll/parse and act loops to allow for individual timings!~
  - Better threading handling now that we hvae threading
- Better examples!
- Formatting on the sample post display in-terminal!
- Checking if the specified post is 'closed' and ignoring inputs if so. For now you just have to remember to turn the script off!
