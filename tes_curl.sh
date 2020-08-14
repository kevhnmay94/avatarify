#!/bin/bash

URL="$1"/avatarify
echo $URL
TOKEN=$(curl -s "$URL" | jq -r '.token')
echo $TOKEN
if [ ! -z "$TOKEN" ]
then
  echo 'change avatar'
  curl -s -F avatar=@avatars/einstein.jpg "$URL"/"$TOKEN"/change_avatar | jq -r '.status'
  milos=(ricardo-milos/*)
  echo 'predict images'
  start=$SECONDS
  for i in "${milos[@]}":
  do
    curl -s -F image=@"$i" "$URL"/"$TOKEN"/predict | jq -r '.status'
  done
  end=$SECONDS
  runtime=$((end-start))
  echo $runtime s
  echo 'logout'
  curl -s "$URL"/"$TOKEN"/logout | jq -r '.status'
else
  echo 'Token is empty'
fi