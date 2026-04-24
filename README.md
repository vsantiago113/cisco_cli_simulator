# Cisco CLI Simulator

This project replays Cisco IOS/IOS-XE command output from captured text files.
Network engineers should collect the commands below from the same device and save
them under either `config/switch/` or `config/router/` using the exact filenames
shown here.

The project includes two sample snapshots:

- `config/switch/` for a Catalyst-style switch
- `config/router/` for an ISR-style router

## Required Files

These three files are required for each device snapshot:

| Command to Run on Device | Save As |
| --- | --- |
| `show version` | `config/<switch-or-router>/Show_Version.txt` |
| `show running-config` | `config/<switch-or-router>/Show_running-config.txt` |
| `show running-config all` | `config/<switch-or-router>/Show_running-config_all.txt` |

## Optional Common Files

These files are useful for both switches and routers. If a file is present, the
simulator returns that captured output exactly. If it is missing, the command may
be unavailable or may use a limited config-derived fallback.

| Command to Run on Device | Save As |
| --- | --- |
| `show interfaces` | `Show_interfaces.txt` |
| `show interfaces description` | `Show_interfaces_description.txt` |
| `show ip interface brief` | `Show_ip_interface_brief.txt` |
| `show ip route` | `Show_ip_route.txt` |
| `show ip arp` | `Show_ip_arp.txt` |
| `show ip cef` | `Show_ip_cef.txt` |
| `show ip protocols` | `Show_ip_protocols.txt` |
| `show access-lists` | `Show_access-lists.txt` |
| `show cdp neighbors` | `Show_cdp_neighbors.txt` |
| `show cdp neighbors detail` | `Show_cdp_neighbors_detail.txt` |
| `show lldp neighbors` | `Show_lldp_neighbors.txt` |
| `show inventory` | `Show_inventory.txt` |
| `show platform` | `Show_platform.txt` |
| `show environment all` | `Show_environment_all.txt` |
| `show license summary` | `Show_license_summary.txt` |
| `show logging` | `Show_logging.txt` |
| `show clock` | `Show_clock.txt` |
| `show users` | `Show_users.txt` |

## Optional Switch Files

Collect these for Catalyst or switching-focused devices:

| Command to Run on Device | Save As |
| --- | --- |
| `show interfaces status` | `config/switch/Show_interfaces_status.txt` |
| `show mac address-table` | `config/switch/Show_mac_address-table.txt` |
| `show spanning-tree` | `config/switch/Show_spanning-tree.txt` |
| `show etherchannel summary` | `config/switch/Show_etherchannel_summary.txt` |
| `show power inline` | `config/switch/Show_power_inline.txt` |

## Optional Router Files

Collect these for routers, WAN edge, firewall-edge routers, or routed switches
when the feature exists:

| Command to Run on Device | Save As |
| --- | --- |
| `show controllers` | `config/router/Show_controllers.txt` |
| `show ip bgp summary` | `config/router/Show_ip_bgp_summary.txt` |
| `show ip ospf neighbor` | `config/router/Show_ip_ospf_neighbor.txt` |
| `show ip eigrp neighbors` | `config/router/Show_ip_eigrp_neighbors.txt` |
| `show ip nat translations` | `config/router/Show_ip_nat_translations.txt` |
| `show ip nat statistics` | `config/router/Show_ip_nat_statistics.txt` |
| `show crypto isakmp sa` | `config/router/Show_crypto_isakmp_sa.txt` |
| `show crypto ipsec sa` | `config/router/Show_crypto_ipsec_sa.txt` |
| `show standby brief` | `config/router/Show_standby_brief.txt` |
| `show vrf` | `config/router/Show_vrf.txt` |
| `show ip vrf` | `config/router/Show_ip_vrf.txt` |

## Engineer Collection Checklist

From the device, run the common captures:

```text
terminal length 0
show version
show running-config
show running-config all
show interfaces
show interfaces description
show ip interface brief
show ip route
show ip arp
show ip cef
show ip protocols
show access-lists
show cdp neighbors
show cdp neighbors detail
show lldp neighbors
show inventory
show platform
show environment all
show license summary
show logging
show clock
show users
```

For switches, also run:

```text
show interfaces status
show mac address-table
show spanning-tree
show etherchannel summary
show power inline
```

For routers or routed WAN-edge devices, also run:

```text
show controllers
show ip bgp summary
show ip ospf neighbor
show ip eigrp neighbors
show ip nat translations
show ip nat statistics
show crypto isakmp sa
show crypto ipsec sa
show standby brief
show vrf
show ip vrf
```

Save each switch command output under `config/switch/`. Save each router command
output under `config/router/`.

## Running the Simulator

Start an interactive prompt:

```bash
python3 main.py
```

Run a single command:

```bash
python3 main.py --command "show version"
python3 main.py --command "show run"
python3 main.py --command "show run all"
python3 main.py --command "show ip route | include Gateway"
```

Set the device type marker when needed:

```bash
python3 main.py --device-type switch
python3 main.py --device-type router
python3 main.py --device-type router --command "show ip nat statistics"
python3 main.py config/router --device-type router
```

The default is `--device-type auto`, which infers the device type from the
captured files and config content. With no path, `python3 main.py` uses
`config/switch/`, while `python3 main.py --device-type router` uses
`config/router/`. A switch snapshot rejects router-only commands, and a router
snapshot rejects switch-only commands, with a Cisco-like invalid input message.

The simulator supports Cisco-style abbreviated commands and output filters such
as `| include`, `| exclude`, `| begin`, and `| section`.

## Python Collection Automation

Use this option when you want a simple Python SSH collector. It uses Paramiko
and saves files directly into the simulator folders.

Install the SSH collection dependency:

```bash
python3 -m pip install -r requirements.txt
```

Preview the commands that will be collected:

```bash
python3 collect_device_outputs.py --device-type switch --list-commands
python3 collect_device_outputs.py --device-type router --list-commands
```

Collect a switch snapshot over SSH:

```bash
python3 collect_device_outputs.py \
  --host 10.99.0.21 \
  --username admin \
  --ask-password \
  --device-type switch
```

Files are saved to:

```text
config/switch/
```

Collect a router snapshot over SSH:

```bash
python3 collect_device_outputs.py \
  --host 10.255.0.1 \
  --username admin \
  --ask-password \
  --device-type router
```

Files are saved to:

```text
config/router/
```

If the login lands at a `>` prompt instead of privileged exec mode, provide an
enable password:

```bash
python3 collect_device_outputs.py \
  --host 10.255.0.1 \
  --username admin \
  --ask-password \
  --ask-enable-password \
  --device-type router
```

The collector sends `terminal length 0` before collecting command output. That
is the Cisco exec command that disables paging and prevents `--More--` prompts.
It saves files under `config/switch/` or `config/router/` unless `--output-dir`
is provided.

## Ansible Collection Automation

Use this option when engineers already use Ansible for network automation. The
playbook uses `device_type` to decide which commands to run and where to save
the files.

Install the required collections:

```bash
ansible-galaxy collection install -r ansible/requirements.yml
```

Edit `ansible/inventory.example.yml` with the real device IPs and usernames.
The example inventory reads passwords from environment variables:

```bash
export ANSIBLE_NET_PASSWORD='your-ssh-password'
export ANSIBLE_ENABLE_PASSWORD='your-enable-password'
```

Collect a switch snapshot with Ansible:

```bash
ansible-playbook \
  -i ansible/inventory.example.yml \
  ansible/collect_device_outputs.yml \
  --limit switch1 \
  -e device_type=switch
```

Files are saved to:

```text
config/switch/
```

Collect a router snapshot with Ansible:

```bash
ansible-playbook \
  -i ansible/inventory.example.yml \
  ansible/collect_device_outputs.yml \
  --limit router1 \
  -e device_type=router
```

Files are saved to:

```text
config/router/
```

Override the output directory when needed:

```bash
ansible-playbook \
  -i ansible/inventory.example.yml \
  ansible/collect_device_outputs.yml \
  --limit router1 \
  -e device_type=router \
  -e output_dir=config/router
```

The playbook also sends `terminal length 0` and `terminal width 512` before
collecting output. Unsupported optional commands are reported and skipped
instead of stopping the entire collection.

## Important Notes

- Capture all files from the same device at about the same time.
- Do not edit prompts into the files; save only the command output.
- Cisco output filters are case-sensitive. For example, `| begin timeout` does
  not match `Timeouts:` with a capital `T`.
- Live operational state cannot be reconstructed perfectly from `show run`.
  For the most accurate simulator behavior, provide the optional operational
  command files.
