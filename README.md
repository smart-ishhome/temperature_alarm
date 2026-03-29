# Temperature Alarm - Home Assistant Custom Integration

<p align="center">
  <img src="Icons/logo_original.png" alt="Temperature Alarm Logo" width="400">
</p>

A Home Assistant custom integration that monitors temperature sensors and triggers binary sensor alerts when temperatures fall outside user-defined ranges.

## Features

- **Multiple Monitoring Modes**:
  - **Minimum Only**: Alert when temperature drops below threshold
  - **Maximum Only**: Alert when temperature exceeds threshold  
  - **Min/Max Range**: Alert when temperature is outside the defined range
- **Device Integration**: Entities attach to the source temperature sensor's device
- **Adjustable Thresholds**: Threshold adjustment via number entities
- **Trigger Delay**: Optional delay before triggering alarm to avoid false positives
- **Multi-language Support**: English, French, German, and Spanish translations

## Installation
### HACS (Recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=smart-ishhome&repository=https%3A%2F%2Fgithub.com%2Fsmart-ishhome%2Ftemperature_alarm)

1. **Ensure HACS is installed:** If you don't have the [Home Assistant Community Store (HACS)](https://hacs.xyz/) installed, follow their instructions to set it up first.
2. **Navigate to HACS:** Open your Home Assistant frontend and go to HACS in the sidebar.
3. **Search for Temperature Alarm:** Search for "Area Occupancy Detection" and select then **Download**.
4. **Restart Home Assistant:** After the download is complete, restart your Home Assistant instance

### Manual Installation 

1. Download the temperature_alarm.zip
 from `https://github.com/smart-ishhome/temperature_alarm/releases`
2. Extract the contents into a **temperature_alarm** folder
3. Copy the `temperature_alarm` folder to your `config/custom_components/` directory
3. Restart Home Assistant

## Configuration

### Initial Setup
1. **Add Integration**:  Go to Settings → Devices & services → Add Integration → Temperature Alarm  
   <br>
   <a href="https://my.home-assistant.io/redirect/config_flow_start?domain=temperature_alarm" class="my badge" target="_blank"><img src="https://my.home-assistant.io/badges/config_flow_start.svg"></a>
   <br>

2. **Select Temperature Sensor**: Choose an existing temperature sensor
3. **Choose Monitoring Mode**:
   - *Minimum*: Alert when too cold
   - *Maximum*: Alert when too hot  
   - *Min/Max Range*: Alert when outside range
4. **Set Initial Thresholds**: Define your temperature limits (adjustable later)
5. **Configure Trigger Delay** (Optional):
   - Enable delay to prevent false alarms from brief temperature spikes
   - Set time delay (seconds) or update count threshold
   - Alarm triggers when EITHER condition is met

### Post-Setup Configuration

After setup, you can:
- Adjust thresholds using the **Minimum Temperature** and **Maximum Temperature** number entities
- Change monitoring mode via **Settings → Devices & Services → Temperature Alarm → Configure**

## Entities Created

For each configured temperature alarm, the integration creates:

| Entity Type | Name | Description |
|-------------|------|-------------|
| Binary Sensor | `Temperature Alarm` | Shows `On` when temperature is outside defined range |
| Number | `Minimum Temperature` | (optional) Adjustable minimum threshold (min/min-max modes) |
| Number | `Maximum Temperature` | (optional) Adjustable maximum threshold (max/min-max modes) |

### Binary Sensor States

- **On (Problem)**: Temperature is outside the defined range
- **Off (Normal)**: Temperature is within acceptable limits
- **Unavailable**: Source temperature sensor is unavailable

### Attributes

The binary sensor provides additional attributes:
- `source_entity`: The monitored temperature sensor
- `mode`: Current monitoring mode (min_only, max_only, min_max)
- `current_temperature`: Current temperature reading
- `min_threshold`: Current minimum threshold (if applicable)
- `max_threshold`: Current maximum threshold (if applicable)
- `delay_enabled`: Whether trigger delay is enabled (if delay configured)
- `delay_time`: Time delay in seconds (if delay configured)
- `delay_updates`: Update count threshold (if delay configured)
- `alarm_pending`: Whether alarm condition exists but hasn't triggered yet (if delay active)
- `alarm_pending_updates`: Number of updates in pending state (if delay active)

## Usage Examples

### Home Heating Alert
Monitor your living room temperature and get alerted when it drops below 68°F:
- **Mode**: Minimum Only
- **Minimum Temperature**: 68°F
- **Use Case**: Trigger heating system and trigger alarmo environmental action

### Server Room Cooling
Monitor server room temperature, shutdown server and alert when it gets too hot:
- **Mode**: Maximum Only  
- **Maximum Temperature**: 80°F
- **Use Case**: Shutdown server and trigger emergency alerts

### Greenhouse Management
Maintain optimal plant growing conditions:
- **Mode**: Min/Max Range
- **Minimum Temperature**: 65°F
- **Maximum Temperature**: 85°F
- **Use Case**: Control heating/cooling/fan systems automatically

### Refrigerator Alert
Monitor your refrigerator temperature and get alerted when it is above 45°F or below 32°F
- **Mode**: Min/Max Range
- **Minimum Temperature**: 32°F
- **Maximum Temperature**: 45°F
- **Trigger Delay**: 5 minutes (300 seconds) to avoid alerts during door opening
- **Use Case**: Send notification to mobile device

## Automation Examples

### Send Notification When Temperature Alarm Triggers

```yaml
automation:
  - alias: "Temperature Alarm Notification"
    trigger:
      platform: state
      entity_id: binary_sensor.living_room_temperature_alarm
      to: "on"
    action:
      - service: notify.mobile_app_your_phone
        data:
          title: "Temperature Alert"
          message: "Living room temperature is {{ state_attr('binary_sensor.living_room_temperature_alarm', 'current_temperature') }}°F (outside safe range)"
```

### Turn On Heater When Too Cold

```yaml
automation:
  - alias: "Auto Heat When Cold"
    trigger:
      platform: state
      entity_id: binary_sensor.bedroom_temperature_alarm
      to: "on"
    condition:
      - condition: template
        value_template: "{{ state_attr('binary_sensor.bedroom_temperature_alarm', 'mode') in ['min_only', 'min_max'] }}"
      - condition: template
        value_template: "{{ state_attr('binary_sensor.bedroom_temperature_alarm', 'current_temperature') < state_attr('binary_sensor.bedroom_temperature_alarm', 'min_threshold') }}"
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.bedroom_heater
```

### Monitor Pending Alarm State

```yaml
automation:
  - alias: "Notify When Alarm Pending"
    trigger:
      platform: template
      value_template: "{{ state_attr('binary_sensor.freezer_temperature_alarm', 'alarm_pending') == true }}"
    action:
      - service: notify.mobile_app_your_phone
        data:
          title: "Temperature Warning"
          message: "Freezer temperature has been out of range for {{ state_attr('binary_sensor.freezer_temperature_alarm', 'alarm_pending_updates') }} updates"
```

## Troubleshooting

### Binary Sensor Not Updating

1. Check that the source temperature sensor is providing valid numeric values
2. Enable debug logging to see state changes:
   ```yaml
   logger:
     logs:
       custom_components.temperature_alarm: debug
   ```
3. Verify threshold entities have valid values (not unavailable)

### Integration Won't Load

1. Ensure all files are copied to the correct directory: `config/custom_components/temperature_alarm/`
2. Restart Home Assistant completely
3. Check `home-assistant.log` for error messages

### Thresholds Not Saving

1. Verify you have write permissions to the Home Assistant configuration directory
2. Check that the `RestoreEntity` data is being saved (should persist across restarts)

## Debug Logging

To enable detailed logging for troubleshooting:

```yaml
# configuration.yaml
logger:
  default: info
  logs:
    custom_components.temperature_alarm: debug
```

Or temporarily via **Developer Tools → Services → Logger: Set Level**:
```yaml
custom_components.temperature_alarm: debug
```

## Contributing

Found a bug or want to contribute? Please:

1. Check existing issues first
2. Create detailed bug reports with logs
3. Submit pull requests with clear descriptions
4. Test changes with multiple temperature sensors

## Language Support

The integration supports multiple languages:
- 🇺🇸 English (default)
- 🇫🇷 French  
- 🇩🇪 German
- 🇪🇸 Spanish

Language is automatically detected from your Home Assistant locale setting.

## License

This project is licensed under the MIT License.

## Version History

- **0.9.0** - Initial release
  - GUI configuration flow
  - Three monitoring modes
  - Adjustable thresholds
  - Device attachment
  - Trigger delay
  - Multi-language support

- **0.9.1** - Feature/bug fix update
  - Added option for threshold entities 
  - Updated Icons
  - Updated min/max limits
  - added debug logs
  - fixed thresold entites not saving after reboot
  - removed icon dir from component dir

- **0.9.2** - 2026.3 icon update
  - Added icons to custom_components/temperature_alarm/brand

- **0.9.3** - Repo/Device Class updates
  - Added .github issue templates
  - Added dependabot configuration
  - Change device class from problem to safety 
  - Updated readme

---

**Need Help?** Check the [troubleshooting section](#troubleshooting) or enable debug logging to diagnose issues.