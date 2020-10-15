#!/bin/bash

git init
find * -size +4M -type f -print >> .gitignore
git add -A
git commit -m "first commit"
git branch -M main
git remote add origin https://raychorn:40b53d4f5adde9d67d4db8678d8ac15b38a94135@github.com/raychorn/svn_openstack-projects.git
git push -u origin main
