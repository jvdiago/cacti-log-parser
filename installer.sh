#!/bin/bash

DEFAULT_DIR=cacti_log_parser
BASE_DIR=/opt
INSTALL_FILE=cacti-log-parser.tar.gz
USER=cacti-log-parser
INIT_FILE=init.redhat
LOGROTATE_FILE=logrotate
INIT_DIR=/etc/init.d
LOGROTATE_DIR=/etc/logrotate.d

if [ $UID != 0 ]; then
	echo "Installer must be run by root"
	exit 1
fi

while getopts ":d:" opt; do
  case $opt in
    d)
      INSTALL_DIR="$OPTARG"
      ;;
    \?)
      echo "Invalid option: -$OPTARG" >&2
      exit 1
      ;;
    :)
      echo "Option -$OPTARG requires an argument." >&2
      exit 1
      ;;
  esac
done

shift $((OPTIND-1))

if [ ! -f $INSTALL_FILE ] || [ ! -f $INIT_FILE ] || [ ! -f $LOGROTATE_FILE ]; then
	echo "File $INSTALL_FILE  or $INIT_FILE or $LOGROTATE_FILE not found"
	exit 2
fi

if [ "$INSTALL_DIR" == '' ]; then
	INSTALL_DIR=$DEFAULT_DIR
fi

if [ -d $INSTALL_DIR ]; then
	echo "The directory $INSTALL_DIR exists. Stopping the installation"
	exit 3 
fi

mkdir -p $BASE_DIR/$INSTALL_DIR


if [ $? != 0 ]; then
	echo "Some problem ocurred when creating $BASE_DIR/$INSTALL_DIR"
	exit 4 
fi

tar -xf $INSTALL_FILE -C $BASE_DIR/$INSTALL_DIR

if [ $? != 0 ]; then
	echo "Some problem ocurred when extracting $INSTALL_FILE"
	exit 5 
fi

cp $INIT_FILE $INIT_DIR/cacti-log-parser
err1=$? 
cp $LOGROTATE_FILE $LOGROTATE_DIR/cacti-log-parser
err2=$?

if [ $err1 != 0 ] || [ $err2 != 0 ]; then
	echo "Some problem ocurred when copying files"
	exit 6 
fi

chmod +x  $INIT_FILE $INIT_DIR/cacti-log-parser
chkconfig cacti-log-parser on

sed -i "s/cacti_log_parser/$INSTALL_DIR/g" $INIT_DIR/cacti-log-parser
sed -i "s/cacti_log_parser/$INSTALL_DIR/g" $LOGROTATE_DIR/cacti-log-parser 
sed -i "s/cacti_log_parser/$INSTALL_DIR/g" $BASE_DIR/$INSTALL_DIR/etc/logging.conf
sed -i "s/DEBUG/INFO/g" $BASE_DIR/$INSTALL_DIR/etc/logging.conf
sed -i "s/cacti_log_parser/$INSTALL_DIR/g" $BASE_DIR/$INSTALL_DIR/etc/parser.ini
sed -i "s/cacti_log_parser/$INSTALL_DIR/g" $BASE_DIR/$INSTALL_DIR/bin/cacti-log-parser.py

echo -e "Please add the next code to your cacti logrotate file\n"
echo -e "postrotate"
echo -e "\t/etc/init.d/cacti-log-parser stop"
echo -e "\t/etc/init.d/cacti-log-parser start"
echo -e "endscript\n"

echo "Installation finished in $INSTALL_DIR"
echo "Configure the daemon option in $BASE_DIR/$INSTALL_DIR/etc/parser.ini"
echo "Run $INIT_DIR/cacti-log-parser to start the daemon"
exit 0 
