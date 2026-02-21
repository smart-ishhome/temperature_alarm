{
  "config": {
    "step": {
      "user": {
        "title": "Temperature Alarm Setup",
        "description": "Select a temperature sensor to monitor for alarm conditions.",
        "data": {
          "source_entity": "Temperature Sensor"
        }
      },
      "mode": {
        "title": "Select Monitoring Mode",
        "description": "Choose how to monitor the temperature.",
        "data": {
          "mode": "Monitoring Mode"
        },
        "data_description": {
          "mode": "Min Only: Alert when below minimum. Max Only: Alert when above maximum. Min/Max: Alert when outside range."
        }
      },
      "thresholds": {
        "title": "Set Temperature Thresholds",
        "description": "Define the temperature thresholds for the alarm. Enable the entity option to allow runtime adjustment.",
        "data": {
          "min_temp": "Minimum Temperature",
          "max_temp": "Maximum Temperature",
          "create_min_entity": "Create adjustable min threshold entity",
          "create_max_entity": "Create adjustable max threshold entity"
        },
        "data_description": {
          "create_min_entity": "When enabled, creates a number entity to adjust the minimum threshold at runtime.",
          "create_max_entity": "When enabled, creates a number entity to adjust the maximum threshold at runtime."
        }
      },
      "delay": {
        "title": "Configure Trigger Delay",
        "description": "Optionally delay the alarm trigger. The alarm will trigger when EITHER the time elapses OR the update count is reached.",
        "data": {
          "delay_enabled": "Enable trigger delay",
          "delay_time": "Time delay (seconds)",
          "delay_updates": "Update count delay"
        },
        "data_description": {
          "delay_enabled": "When enabled, the alarm will wait before triggering.",
          "delay_time": "Trigger alarm after this many seconds in alarm condition.",
          "delay_updates": "Trigger alarm after this many sensor updates in alarm condition."
        }
      }
    },
    "error": {
      "invalid_entity": "Selected entity is not a valid temperature sensor.",
      "min_greater_than_max": "Minimum temperature must be less than maximum temperature."
    },
    "abort": {
      "already_configured": "This sensor is already configured for temperature alarm monitoring."
    }
  },
  "options": {
    "step": {
      "init": {
        "title": "Temperature Alarm Options",
        "description": "Modify the temperature alarm configuration.",
        "data": {
          "mode": "Monitoring Mode",
          "min_temp": "Minimum Temperature",
          "max_temp": "Maximum Temperature",
          "create_min_entity": "Create adjustable min threshold entity",
          "create_max_entity": "Create adjustable max threshold entity",
          "delay_enabled": "Enable trigger delay",
          "delay_time": "Time delay (seconds)",
          "delay_updates": "Update count delay"
        }
      }
    },
    "error": {
      "min_greater_than_max": "Minimum temperature must be less than maximum temperature."
    }
  },
  "entity": {
    "binary_sensor": {
      "temperature_alarm": {
        "name": "Temperature Alarm"
      }
    },
    "number": {
      "min_temperature": {
        "name": "Minimum Temperature"
      },
      "max_temperature": {
        "name": "Maximum Temperature"
      }
    }
  }
}
