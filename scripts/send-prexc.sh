echo -ne '\033]0;send-prexc\007'
ssh comtor@netport.mediport.com.co -t 'cd /opt/comtor-dev/mediport-automation-2 && exec bash -l'
echo -ne '\033]0;send-prexc\007'
exec bash
