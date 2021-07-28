# Fisherbrand balance
This repo contains a python script to automate recording measurements from a Fisherbrand balance.
The specific balance that this repo has been written and tested with is the Fisherbrand 15??????

## Running the script
Use a text editor to adjust the SECONDS_BETWEEN_MEASUREMENTS parameter in the balance_recorder.py. Then run the
following command...
```shell
python balance_recorder.py
```

## Linux: Allowing non-root access to usb
Running ```groups``` might show that user isn't a member of the 'dialout' group

Running the command below will add the current user to the dialout group enabling non-root access to the usb ports
```
sudo usermod -a -G dialout $USER
```