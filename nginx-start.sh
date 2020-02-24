#!/bin/sh

sed "s|SOURCE_ROOT|$(pwd)|" nginx.conf.template > nginx.conf
nginx -c $(pwd)/nginx.conf
echo "**** Access running server at http://localhost:8080 ****"
