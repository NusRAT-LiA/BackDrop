
### Environment Interaction 1
----------------------------------------------------------------------------
```python
print(apis.api_docs.show_api_descriptions(app_name='phone'))
```

```
[
 {
  "name": "show_account",
  "description": "Show your account information. Unlike show_profile, this includes private information."
 },
 {
  "name": "signup",
  "description": "Sign up to create account."
 },
 {
  "name": "delete_account",
  "description": "Delete your account."
 },
 {
  "name": "update_account_name",
  "description": "Update your first or last name in the account profile."
 },
 {
  "name": "login",
  "description": "Login to your account."
 },
 {
  "name": "logout",
  "description": "Logout from your account."
 },
 {
  "name": "send_password_reset_code",
  "description": "Send password reset code to your phone number."
 },
 {
  "name": "reset_password",
  "description": "Reset your password using the password reset code sent to your email address."
 },
 {
  "name": "show_profile",
  "description": "Show public profile information of a user."
 },
 {
  "name": "show_contact_relationships",
  "description": "Get a list of all relationships available in your contact book."
 },
 {
  "name": "search_contacts",
  "description": "Search your contact book for relatives' information."
 },
 {
  "name": "add_contact",
  "description": "Add a new contact."
 },
 {
  "name": "update_contact",
  "description": "Update contact information."
 },
 {
  "name": "delete_contact",
  "description": "Delete contact information."
 },
 {
  "name": "show_text_message_window",
  "description": "Show text messages with a contact around a given date and time."
 },
 {
  "name": "search_text_messages",
  "description": "Show or search your text messages."
 },
 {
  "name": "show_text_message",
  "description": "Show text message details."
 },
 {
  "name": "delete_text_message",
  "description": "Delete a text message."
 },
 {
  "name": "send_text_message",
  "description": "Send a text message on the given phone number."
 },
 {
  "name": "show_alarms",
  "description": "Get a list of alarms."
 },
 {
  "name": "create_alarm",
  "description": "Create a new alarm."
 },
 {
  "name": "show_alarm",
  "description": "Show alarm details."
 },
 {
  "name": "update_alarm",
  "description": "Update an alarm's settings."
 },
 {
  "name": "delete_alarm",
  "description": "Delete an alarm."
 },
 {
  "name": "show_voice_message_window",
  "description": "Show voice messages with a contact around a given date and time."
 },
 {
  "name": "search_voice_messages",
  "description": "Show or search text voice_messages between the user and a contact."
 },
 {
  "name": "show_voice_message",
  "description": "Show voice message details."
 },
 {
  "name": "delete_voice_message",
  "description": "Delete a voice message."
 },
 {
  "name": "send_voice_message",
  "description": "Send a voice message on the given phone number."
 },
 {
  "name": "get_current_date_and_time",
  "description": "Show current date and time."
 }
]
```


### Environment Interaction 2
----------------------------------------------------------------------------
```python
passwords = apis.supervisor.show_account_passwords()
password_map = {p["account_name"]: p["password"] for p in passwords}
print(password_map.keys())
print(apis.api_docs.show_api_doc(app_name='phone', api_name='login'))
```

```
dict_keys(['amazon', 'file_system', 'gmail', 'phone', 'simple_note', 'splitwise', 'spotify', 'todoist', 'venmo'])
{
 "app_name": "phone",
 "api_name": "login",
 "path": "/phone/auth/token",
 "method": "POST",
 "description": "Login to your account.",
 "parameters": [
  {
   "name": "username",
   "type": "string",
   "required": true,
   "description": "Your account phone_number.",
   "default": null,
   "constraints": []
  },
  {
   "name": "password",
   "type": "string",
   "required": true,
   "description": "Your account password.",
   "default": null,
   "constraints": []
  }
 ],
 "response_schemas": {
  "success": {
   "access_token": "string",
   "token_type": "string"
  },
  "failure": {
   "message": "string"
  }
 }
}
```


### Environment Interaction 3
----------------------------------------------------------------------------
```python
phone_login = apis.phone.login(username='3517418245', password=password_map['phone'])
phone_token = phone_login['access_token']
print(apis.api_docs.show_api_doc(app_name='phone', api_name='search_contacts'))
```

```
{
 "app_name": "phone",
 "api_name": "search_contacts",
 "path": "/phone/contacts",
 "method": "GET",
 "description": "Search your contact book for relatives' information.",
 "parameters": [
  {
   "name": "access_token",
   "type": "string",
   "required": true,
   "description": "Access token obtained from phone app login.",
   "default": null,
   "constraints": []
  },
  {
   "name": "query",
   "type": "string",
   "required": false,
   "description": "Search query for the contacts list.",
   "default": "",
   "constraints": []
  },
  {
   "name": "relationship",
   "type": "string",
   "required": false,
   "description": "Relationship with the person in the contacts list to filter by.",
   "default": null,
   "constraints": []
  },
  {
   "name": "page_index",
   "type": "integer",
   "required": false,
   "description": "The index of the page to return.",
   "default": 0,
   "constraints": [
    "value >= 0"
   ]
  },
  {
   "name": "page_limit",
   "type": "integer",
   "required": false,
   "description": "The maximum number of results to return per page.",
   "default": 5,
   "constraints": [
    "value >= 1, <= 20"
   ]
  }
 ],
 "response_schemas": {
  "success": [
   {
    "contact_id": 1,
    "first_name": "string",
    "last_name": "string",
    "email": "user@example.com",
    "phone_number": "string",
    "relationships": [
     "string"
    ],
    "birthday": "string",
    "home_address": "string",
    "work_address": "string",
    "created_at": "2019-01-01T00:00:00"
   }
  ],
  "failure": {
   "message": "string"
  }
 }
}
```


### Environment Interaction 4
----------------------------------------------------------------------------
```python
print(apis.phone.show_contact_relationships(access_token=phone_token))
```

```
[
 "brother",
 "coworker",
 "father",
 "friend",
 "husband",
 "mother",
 "parent",
 "partner",
 "sibling",
 "sister",
 "subordinate"
]
```


### Environment Interaction 5
----------------------------------------------------------------------------
```python
siblings = []
for rel in ["brother", "sister", "sibling"]:
    page_index = 0
    while True:
        page = apis.phone.search_contacts(access_token=phone_token, relationship=rel, page_index=page_index, page_limit=20)
        if not page:
            break
        siblings.extend(page)
        page_index += 1
# dedupe
seen = set()
unique_siblings = []
for s in siblings:
    if s['contact_id'] not in seen:
        seen.add(s['contact_id'])
        unique_siblings.append(s)
for s in unique_siblings:
    print(s['contact_id'], s['first_name'], s['last_name'], s['phone_number'], s['email'], s['relationships'])
```

```
1034 Joseph Weber 2233697879 joseph.webe@gmail.com ['sibling', 'brother']
1032 Nicholas Weber 9503658964 nicholas.weber@gmail.com ['sibling', 'brother']
1033 Brenda Smith 9312015677 brenda.webe@gmail.com ['sibling', 'sister']
```


### Environment Interaction 6
----------------------------------------------------------------------------
```python
print(apis.api_docs.show_api_doc(app_name='phone', api_name='search_text_messages'))
```

```
{
 "app_name": "phone",
 "api_name": "search_text_messages",
 "path": "/phone/messages/text",
 "method": "GET",
 "description": "Show or search your text messages.",
 "parameters": [
  {
   "name": "access_token",
   "type": "string",
   "required": true,
   "description": "Access token obtained from phone app login.",
   "default": null,
   "constraints": []
  },
  {
   "name": "query",
   "type": "string",
   "required": false,
   "description": "The search query string.",
   "default": "",
   "constraints": []
  },
  {
   "name": "phone_number",
   "type": "string",
   "required": false,
   "description": "The phone number of the contact to show messages with.",
   "default": null,
   "constraints": []
  },
  {
   "name": "only_latest_per_contact",
   "type": "boolean",
   "required": false,
   "description": "If set to true, only the latest message from each contact will be shown.",
   "default": false,
   "constraints": []
  },
  {
   "name": "page_index",
   "type": "integer",
   "required": false,
   "description": "The index of the page to return.",
   "default": 0,
   "constraints": [
    "value >= 0"
   ]
  },
  {
   "name": "page_limit",
   "type": "integer",
   "required": false,
   "description": "The maximum number of results to return per page.",
   "default": 5,
   "constraints": [
    "value >= 1, <= 20"
   ]
  },
  {
   "name": "sort_by",
   "type": "string",
   "required": false,
   "description": "The attribute to sort the messages by prefixed with +/- to reflect ascending/descending. Valid attributes: created_at. If both query and sort_by are given and non-empty, results will be first ranked by query relevance, then paginated, and will then be sorted by the given attribute within each page. If both query and sort_by are not given, null, or empty, sort_by will default to -created_at.",
   "default": null,
   "constraints": []
  }
 ],
 "response_schemas": {
  "success": [
   {
    "text_message_id": 1,
    "sender": {
     "contact_id": 1,
     "name": "string",
     "phone_number": "string"
    },
    "receiver": {
     "contact_id": 1,
     "name": "string",
     "phone_number": "string"
    },
    "message": "string",
    "sent_at": "2019-01-01T00:00:00"
   }
  ],
  "failure": {
   "message": "string"
  }
 }
}
```


### Environment Interaction 7
----------------------------------------------------------------------------
```python
all_msgs = {}
for s in unique_siblings:
    page_index = 0
    while True:
        page = apis.phone.search_text_messages(access_token=phone_token, phone_number=s['phone_number'], page_index=page_index, page_limit=20)
        if not page:
            break
        for m in page:
            all_msgs[m['text_message_id']] = m
        page_index += 1
msgs = sorted(all_msgs.values(), key=lambda m: m['sent_at'])
for m in msgs:
    print(m['sent_at'], '|', m['sender']['name'], '->', m['receiver']['name'], '|', m['message'])
```

```
2022-07-30T08:50:27 | Nicholas Weber -> Cheryl Martinez | Happy Birthday, sibling! From childhood memories to the present, you've always been my rock. Enjoy your day!
2022-07-30T09:24:23 | Cheryl Martinez -> Nicholas Weber | Thank you, sibling! Your words mean the world. Excited to celebrate together!
2022-07-30T10:07:48 | Nicholas Weber -> Cheryl Martinez | Here's to many more shared laughs, secrets, and adventures. Happy birthday!
2022-10-22T16:40:29 | Cheryl Martinez -> Brenda Smith | Happy Birthday, sibling! From childhood memories to the present, you've always been my rock. Enjoy your day!
2022-10-22T17:01:58 | Brenda Smith -> Cheryl Martinez | Thank you, sibling! Your words mean the world. Excited to celebrate together!
2022-10-22T17:29:56 | Cheryl Martinez -> Brenda Smith | Here's to many more shared laughs, secrets, and adventures. Happy birthday!
2023-05-17T17:34:25 | Cheryl Martinez -> Joseph Weber | I am putting together this playlist for our roadtrip => https://spotify.com/playlists/654. Do you have any suggestions?
2023-05-17T17:34:25 | Cheryl Martinez -> Nicholas Weber | I am putting together this playlist for our roadtrip => https://spotify.com/playlists/654. Do you have any suggestions?
2023-05-17T17:34:25 | Cheryl Martinez -> Brenda Smith | I am putting together this playlist for our roadtrip => https://spotify.com/playlists/654. Do you have any suggestions?
2023-05-17T17:39:06 | Nicholas Weber -> Cheryl Martinez | Yes! I have a few suggestions.
add => Shadows in the Twilight by Silent Thunder
remove => In the Chambers of My Mind by Jasper Skye
remove => Ashes and Roses by Seraphina Dawn
remove => When Dreams Begin to Crumble by Oceanic Odyssey

2023-05-17T19:13:37 | Joseph Weber -> Cheryl Martinez | No suggestions, looks good to me!
2023-05-17T19:31:54 | Brenda Smith -> Cheryl Martinez | Yes! I have a few suggestions.
add => Dancing on the Precipice of Love by Eliana Harper
add => Midnight Whispers by Silent Thunder
add => Lost in the Symphony of Time by Nova Harmony
remove => Velvet Skies by Lucas Diaz
```


### Environment Interaction 8
----------------------------------------------------------------------------
```python
spotify_login = apis.spotify.login(username='cheweber@gmail.com', password=password_map['spotify'])
spotify_token = spotify_login['access_token']
print(apis.api_docs.show_api_doc(app_name='spotify', api_name='show_playlist'))
```

```
{
 "app_name": "spotify",
 "api_name": "show_playlist",
 "path": "/spotify/playlists/{playlist_id}",
 "method": "GET",
 "description": "Get detailed information about a specific playlist. You can view your own playlists or others' playlists if they are public.",
 "parameters": [
  {
   "name": "playlist_id",
   "type": "integer",
   "required": true,
   "description": "The playlist id to retrieve.",
   "default": null,
   "constraints": []
  },
  {
   "name": "access_token",
   "type": "string",
   "required": false,
   "description": "Access token obtained from spotify app login.",
   "default": null,
   "constraints": []
  }
 ],
 "response_schemas": {
  "success": {
   "playlist_id": 1,
   "title": "string",
   "is_public": true,
   "rating": 0.0,
   "like_count": 1,
   "review_count": 1,
   "owner": {
    "name": "string",
    "email": "user@example.com"
   },
   "created_at": "2019-01-01T00:00:00",
   "shareable_link": "string",
   "songs": [
    {
     "id": 1,
     "title": "string",
     "album_id": 1,
     "album_title": "string",
     "duration": 1,
     "artists": [
      {
       "id": 1,
       "name": "string"
      }
     ]
    }
   ]
  },
  "failure": {
   "message": "string"
  }
 }
}
```


### Environment Interaction 9
----------------------------------------------------------------------------
```python
playlist = apis.spotify.show_playlist(playlist_id=654, access_token=spotify_token)
print(playlist['title'], playlist['owner'])
for s in playlist['songs']:
    print(s['id'], '|', s['title'], '|', [a['name'] for a in s['artists']])
```

```
Road Trip {'name': 'Cheryl Martinez', 'email': 'cheweber@gmail.com'}
6 | Reflections in a Pool of Regret | ['Jasper Skye', 'Isabella Cruz', 'Seraphina Dawn']
11 | Lost in a Moment's Grace | ['Apollo Serenade', 'Phoenix Rivers']
16 | Yearning for a Glimpse of Heaven | ['Noah Bennett']
32 | Wading Through Rivers of Tears | ['Noah Bennett', 'Ethan Wallace', 'Nova Harmony']
68 | Lost in the Wilderness of Love | ['Lily Moon', 'Zoey James']
96 | In the Chambers of My Mind | ['Jasper Skye']
106 | The Irony of a Perfect Moment | ['Ava Morgan']
115 | Ashes and Roses | ['Seraphina Dawn']
119 | Urban Jungle | ['Orion Steele']
132 | Shadow Dance | ['Aria Sterling']
163 | Veiled Sorrow | ['Grace Harrison']
164 | Waiting for the Morning Light | ['Grace Harrison']
166 | In the Embrace of Solitude | ['Grace Harrison']
182 | Melodies of the Forgotten Past | ['Apollo Serenade']
198 | The Last Embers of a Fire | ['Astrid Nightshade']
215 | When Dreams Begin to Crumble | ['Oceanic Odyssey']
218 | Lost in the Tumult of Emotions | ['Oceanic Odyssey']
234 | Azure Skies | ['Liam Palmer']
250 | Invisible Chains | ['Velvet Echo']
276 | Velvet Skies | ['Lucas Diaz']
318 | Mystic Voyage to Avalon | ['Nova Harmony']
321 | Drowning in a Sea of Regret | ['Noah Bennett']
```


### Environment Interaction 10
----------------------------------------------------------------------------
```python
to_remove = [
    ("In the Chambers of My Mind", "Jasper Skye"),
    ("Ashes and Roses", "Seraphina Dawn"),
    ("When Dreams Begin to Crumble", "Oceanic Odyssey"),
    ("Velvet Skies", "Lucas Diaz"),
]
to_add = [
    ("Shadows in the Twilight", "Silent Thunder"),
    ("Dancing on the Precipice of Love", "Eliana Harper"),
    ("Midnight Whispers", "Silent Thunder"),
    ("Lost in the Symphony of Time", "Nova Harmony"),
]
remove_ids = []
for title, artist in to_remove:
    matches = [s for s in playlist['songs'] if s['title'] == title and artist in [a['name'] for a in s['artists']]]
    print(title, artist, '->', [m['id'] for m in matches])
    remove_ids.extend([m['id'] for m in matches])
print(remove_ids)
print(apis.api_docs.show_api_doc(app_name='spotify', api_name='search_songs'))
```

```
In the Chambers of My Mind Jasper Skye -> [96]
Ashes and Roses Seraphina Dawn -> [115]
When Dreams Begin to Crumble Oceanic Odyssey -> [215]
Velvet Skies Lucas Diaz -> [276]
[96, 115, 215, 276]
{
 "app_name": "spotify",
 "api_name": "search_songs",
 "path": "/spotify/songs",
 "method": "GET",
 "description": "Search for songs with a query.",
 "parameters": [
  {
   "name": "query",
   "type": "string",
   "required": false,
   "description": "The search query string.",
   "default": "",
   "constraints": []
  },
  {
   "name": "artist_id",
   "type": "integer",
   "required": false,
   "description": "The artist id to filter the search results by.",
   "default": null,
   "constraints": []
  },
  {
   "name": "album_id",
   "type": "integer",
   "required": false,
   "description": "The album id to filter the search results by.",
   "default": null,
   "constraints": []
  },
  {
   "name": "genre",
   "type": "string",
   "required": false,
   "description": "The genre to filter the albums by.",
   "default": null,
   "constraints": []
  },
  {
   "name": "min_release_date",
   "type": "string",
   "required": false,
   "description": "The minimum release date for search results in YYYY-MM-DD format.",
   "default": "1500-01-01",
   "constraints": []
  },
  {
   "name": "max_release_date",
   "type": "string",
   "required": false,
   "description": "The maximum release date for search results in YYYY-MM-DD format.",
   "default": "3000-01-01",
   "constraints": []
  },
  {
   "name": "min_duration",
   "type": "integer",
   "required": false,
   "description": "The minimum duration in seconds for search results.",
   "default": 0,
   "constraints": [
    "value >= 0"
   ]
  },
  {
   "name": "max_duration",
   "type": "integer",
   "required": false,
   "description": "The maximum duration in seconds for search results.",
   "default": 9223372036854775807,
   "constraints": [
    "value >= 0"
   ]
  },
  {
   "name": "min_rating",
   "type": "number",
   "required": false,
   "description": "The minimum rating for search results.",
   "default": 0.0,
   "constraints": [
    "value >= 0.0, <= 5.0"
   ]
  },
  {
   "name": "max_rating",
   "type": "number",
   "required": false,
   "description": "The maximum rating for search results.",
   "default": 5.0,
   "constraints": [
    "value >= 0.0, <= 5.0"
   ]
  },
  {
   "name": "min_like_count",
   "type": "integer",
   "required": false,
   "description": "The minimum like count for search results.",
   "default": 0,
   "constraints": [
    "value >= 0"
   ]
  },
  {
   "name": "max_like_count",
   "type": "integer",
   "required": false,
   "description": "The maximum like count for search results.",
   "default": 9223372036854775807,
   "constraints": [
    "value >= 0"
   ]
  },
  {
   "name": "min_play_count",
   "type": "integer",
   "required": false,
   "description": "The minimum play count for search results.",
   "default": 0,
   "constraints": [
    "value >= 0"
   ]
  },
  {
   "name": "max_play_count",
   "type": "integer",
   "required": false,
   "description": "The maximum play count for search results.",
   "default": 9223372036854775807,
   "constraints": [
    "value >= 0"
   ]
  },
  {
   "name": "page_index",
   "type": "integer",
   "required": false,
   "description": "The index of the page to return.",
   "default": 0,
   "constraints": [
    "value >= 0"
   ]
  },
  {
   "name": "page_limit",
   "type": "integer",
   "required": false,
   "description": "The maximum number of results to return per page.",
   "default": 5,
   "constraints": [
    "value >= 1, <= 20"
   ]
  },
  {
   "name": "sort_by",
   "type": "string",
   "required": false,
   "description": "The attribute to sort the songs by prefixed with +/- to reflect ascending/descending. Valid attributes: rating, like_count and play_count. If both query and sort_by are given and non-empty, results will be first ranked by query relevance, then paginated, and will then be sorted by the given attribute within each page.",
   "default": null,
   "constraints": []
  }
 ],
 "response_schemas": {
  "success": [
   {
    "song_id": 1,
    "title": "string",
    "album_id": 1,
    "album_title": "string",
    "duration": 1,
    "artists": [
     {
      "id": 1,
      "name": "string"
     }
    ],
    "release_date": "2019-01-01T00:00:00",
    "genre": "string",
    "play_count": 0.0,
    "rating": 0.0,
    "like_count": 1,
    "review_count": 1,
    "shareable_link": "string"
   }
  ],
  "failure": {
   "message": "string"
  }
 }
}
```


### Environment Interaction 11
----------------------------------------------------------------------------
```python
add_ids = []
for title, artist in to_add:
    results = apis.spotify.search_songs(query=title, page_limit=20)
    matches = [r for r in results if r['title'].lower() == title.lower() and artist in [a['name'] for a in r['artists']]]
    print(title, artist, '->', [(m['song_id'], m['title'], [a['name'] for a in m['artists']]) for m in matches])
    if len(matches) == 1:
        add_ids.append(matches[0]['song_id'])
print(add_ids)
```

```
Shadows in the Twilight Silent Thunder -> [(225, 'Shadows in the Twilight', ['Silent Thunder'])]
Dancing on the Precipice of Love Eliana Harper -> [(148, 'Dancing on the Precipice of Love', ['Eliana Harper'])]
Midnight Whispers Silent Thunder -> [(226, 'Midnight Whispers', ['Silent Thunder'])]
Lost in the Symphony of Time Nova Harmony -> [(316, 'Lost in the Symphony of Time', ['Nova Harmony'])]
[225, 148, 226, 316]
```


### Environment Interaction 12
----------------------------------------------------------------------------
```python
print(apis.api_docs.show_api_doc(app_name='spotify', api_name='add_song_to_playlist'))
print(apis.api_docs.show_api_doc(app_name='spotify', api_name='remove_song_from_playlist'))
```

```
{
 "app_name": "spotify",
 "api_name": "add_song_to_playlist",
 "path": "/spotify/playlists/{playlist_id}/songs/{song_id}",
 "method": "POST",
 "description": "Add a song to a playlist.",
 "parameters": [
  {
   "name": "playlist_id",
   "type": "integer",
   "required": true,
   "description": "The playlist id to add the song to.",
   "default": null,
   "constraints": []
  },
  {
   "name": "song_id",
   "type": "integer",
   "required": true,
   "description": "The song id to add.",
   "default": null,
   "constraints": []
  },
  {
   "name": "access_token",
   "type": "string",
   "required": true,
   "description": "Access token obtained from spotify app login.",
   "default": null,
   "constraints": []
  }
 ],
 "response_schemas": {
  "success": {
   "message": "string"
  },
  "failure": {
   "message": "string"
  }
 }
}
{
 "app_name": "spotify",
 "api_name": "remove_song_from_playlist",
 "path": "/spotify/playlists/{playlist_id}/songs/{song_id}",
 "method": "DELETE",
 "description": "Remove a song from a playlist.",
 "parameters": [
  {
   "name": "playlist_id",
   "type": "integer",
   "required": true,
   "description": "The playlist id to remove the song from.",
   "default": null,
   "constraints": []
  },
  {
   "name": "song_id",
   "type": "integer",
   "required": true,
   "description": "The song id to remove.",
   "default": null,
   "constraints": []
  },
  {
   "name": "access_token",
   "type": "string",
   "required": true,
   "description": "Access token obtained from spotify app login.",
   "default": null,
   "constraints": []
  }
 ],
 "response_schemas": {
  "success": {
   "message": "string"
  },
  "failure": {
   "message": "string"
  }
 }
}
```


### Environment Interaction 13
----------------------------------------------------------------------------
```python
for sid in remove_ids:
    print('remove', sid, apis.spotify.remove_song_from_playlist(playlist_id=654, song_id=sid, access_token=spotify_token))
for sid in add_ids:
    print('add', sid, apis.spotify.add_song_to_playlist(playlist_id=654, song_id=sid, access_token=spotify_token))
```

```
remove 96 {'message': 'Song removed from playlist.'}
remove 115 {'message': 'Song removed from playlist.'}
remove 215 {'message': 'Song removed from playlist.'}
remove 276 {'message': 'Song removed from playlist.'}
add 225 {'message': 'Song added to the playlist.'}
add 148 {'message': 'Song added to the playlist.'}
add 226 {'message': 'Song added to the playlist.'}
add 316 {'message': 'Song added to the playlist.'}
```


### Environment Interaction 14
----------------------------------------------------------------------------
```python
playlist = apis.spotify.show_playlist(playlist_id=654, access_token=spotify_token)
ids = [s['id'] for s in playlist['songs']]
print(len(ids))
print('removed ok:', all(r not in ids for r in remove_ids))
print('added ok:', all(a in ids for a in add_ids))
```

```
22
removed ok: True
added ok: True
```


### Environment Interaction 15
----------------------------------------------------------------------------
```python
apis.supervisor.complete_task()
```

```
Execution successful.
```

