TODAY=$(date +%Y-%m-%d)
echo -ne '\033]0;logs-aixa\007'
ssh -p 56789 jaimeandres@154.38.166.214 "sudo su - aixabot -c 'tail -f -n500 /opt/miia_core2/logs/aixa-${TODAY}.log'"
echo -ne '\033]0;logs-aixa\007o -ne '\033]0;logs-aixa\007'
ssh -p 56789 jaimeandres@154.38.166.214 '
exec bash
