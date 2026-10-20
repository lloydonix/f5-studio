-- F5-TTS launcher: starts the Gradio web UI and opens it in the browser.
-- Stays in the Dock while running; Quit (Cmd-Q / Dock > Quit) stops the server.
property appURL : "http://127.0.0.1:7860"
property serverPID : ""
property opened : false

on portUp()
	return (do shell script "/usr/sbin/lsof -ti tcp:7860 -sTCP:LISTEN 2>/dev/null || true") is not ""
end portUp

on run
	set serverPID to ""
	set opened to false
	if portUp() then
		open location appURL
		set opened to true
	else
		set serverPID to do shell script "export PATH=/opt/homebrew/bin:$PATH HF_HUB_OFFLINE=1; cd ~/f5-tts; nohup ~/f5-tts/.venv/bin/f5-tts_infer-gradio --host 127.0.0.1 --port 7860 > ~/f5-tts/f5-tts.log 2>&1 < /dev/null & echo $!"
		display notification "Loading models… the browser opens when it's ready." with title "F5-TTS"
	end if
end run

on idle
	if not opened then
		if portUp() then
			open location appURL
			set opened to true
		else if serverPID is not "" then
			if (do shell script "kill -0 " & serverPID & " 2>/dev/null && echo alive || echo dead") is "dead" then
				display dialog "F5-TTS failed to start. See ~/f5-tts/f5-tts.log" with title "F5-TTS" buttons {"OK"} with icon stop
				quit
			end if
		end if
		return 2
	end if
	return 30
end idle

on reopen
	if opened then open location appURL
end reopen

on quit
	if serverPID is not "" then
		do shell script "pkill -P " & serverPID & " 2>/dev/null; kill " & serverPID & " 2>/dev/null || true"
	end if
	continue quit
end quit
