import logging
from typing import Optional

import voluptuous as vol

from homeassistant.core import callback
from homeassistant.components.sensor import ENTITY_ID_FORMAT, \
    PLATFORM_SCHEMA, DEVICE_CLASSES_SCHEMA
from homeassistant.const import (
    ATTR_FRIENDLY_NAME, ATTR_UNIT_OF_MEASUREMENT, CONF_ICON_TEMPLATE,
	CONF_ENTITY_PICTURE_TEMPLATE, CONF_SENSORS, EVENT_HOMEASSISTANT_START,
	MATCH_ALL, CONF_DEVICE_CLASS, DEVICE_CLASS_TEMPERATURE, STATE_UNKNOWN,
        DEVICE_CLASS_HUMIDITY, ATTR_TEMPERATURE)
from homeassistant.exceptions import TemplateError
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import Entity, async_generate_entity_id
from homeassistant.helpers.event import async_track_state_change

import math

_LOGGER = logging.getLogger(__name__)

CONF_TEMPERATURE_SENSOR = 'temperature_sensor'
CONF_HUMIDITY_SENSOR = 'humidity_sensor'
ATTR_HUMIDITY = 'humidity'

SENSOR_SCHEMA = vol.Schema({
    vol.Required(CONF_TEMPERATURE_SENSOR): cv.entity_id,
    vol.Required(CONF_HUMIDITY_SENSOR): cv.entity_id,
    vol.Optional(CONF_ICON_TEMPLATE): cv.template,
    vol.Optional(CONF_ENTITY_PICTURE_TEMPLATE): cv.template,
    vol.Optional(ATTR_FRIENDLY_NAME): cv.string
})

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_SENSORS): cv.schema_with_slug_keys(SENSOR_SCHEMA),
})

SENSOR_TYPES = {
    'umidita_assoluta': [DEVICE_CLASS_HUMIDITY, 'Umidità assoluta', 'g/m³'],
    'indice_di_calore': [DEVICE_CLASS_TEMPERATURE, 'Indice di Calore', '°C'],
    'punto_di_rugiada': [DEVICE_CLASS_TEMPERATURE, 'Punto di Rugiada', '°C'],
    'percepita': [None, 'Temperatura Percepita', None],
    'punto_di_congelamento': [DEVICE_CLASS_TEMPERATURE, 'Punto di Congelamento', '°C'],	
##    'livello_di_rischio': [None, 'Livello di Rischio', None],
}

async def async_setup_platform(hass, config, async_add_entities,
                               discovery_info=None):
    """Set up the Thermal Comfort sensors."""
    sensors = []

    for device, device_config in config[CONF_SENSORS].items():
        temperature_entity = device_config.get(CONF_TEMPERATURE_SENSOR)
        humidity_entity = device_config.get(CONF_HUMIDITY_SENSOR)
        icon_template = device_config.get(CONF_ICON_TEMPLATE)
        entity_picture_template = device_config.get(CONF_ENTITY_PICTURE_TEMPLATE)
        friendly_name = device_config.get(ATTR_FRIENDLY_NAME, device)

        for sensor_type in SENSOR_TYPES:
                sensors.append(
                        SensorThermalComfort(
                                hass,
                                device,
                                temperature_entity,
                                humidity_entity,
                                friendly_name,
                                icon_template,
                                entity_picture_template,
                                sensor_type)
                        )
    if not sensors:
        _LOGGER.error("No sensors added")
        return False

    async_add_entities(sensors)
    return True


class SensorThermalComfort(Entity):
    """Representation of a Thermal Comfort Sensor."""

    def __init__(self, hass, device_id, temperature_entity, humidity_entity,
                 friendly_name, icon_template, entity_picture_template, sensor_type):
        """Initialize the sensor."""
        self.hass = hass
        self.entity_id = async_generate_entity_id(ENTITY_ID_FORMAT, "{}_{}".format(device_id, sensor_type), hass=hass)
        self._name = "{} {}".format(friendly_name, SENSOR_TYPES[sensor_type][1])
        self._unit_of_measurement = SENSOR_TYPES[sensor_type][2]
        self._state = None
        self._device_state_attributes = {}
        self._icon_template = icon_template
        self._entity_picture_template = entity_picture_template
        self._icon = None
        self._entity_picture = None
        self._temperature_entity = temperature_entity
        self._humidity_entity = humidity_entity
        self._device_class = SENSOR_TYPES[sensor_type][0]
        self._sensor_type = sensor_type
        self._temperature = None
        self._humidity = None

        async_track_state_change(
            self.hass, self._temperature_entity, self.temperature_state_listener)

        async_track_state_change(
            self.hass, self._humidity_entity, self.humidity_state_listener)

        temperature_state = hass.states.get(temperature_entity)
        if temperature_state and temperature_state.state != STATE_UNKNOWN:
            self._temperature = float(temperature_state.state)

        humidity_state = hass.states.get(humidity_entity)
        if humidity_state and humidity_state.state != STATE_UNKNOWN:
            self._humidity = float(humidity_state.state)

    def temperature_state_listener(self, entity, old_state, new_state):
        """Handle temperature device state changes."""
        if new_state and new_state.state != STATE_UNKNOWN:
            self._temperature = float(new_state.state)

        self.async_schedule_update_ha_state(True)

    def humidity_state_listener(self, entity, old_state, new_state):
        """Handle humidity device state changes."""
        if new_state and new_state.state != STATE_UNKNOWN:
            self._humidity = float(new_state.state)

        self.async_schedule_update_ha_state(True)

    def computePunto_Di_Rugiada(self, temperature, humidity):
        """http://wahiduddin.net/calc/density_algorithms.htm"""
        A0 = 373.15 / (273.15 + temperature)
        SUM = -7.90298 * (A0 - 1)
        SUM += 5.02808 * math.log(A0, 10)
        SUM += -1.3816e-7 * (pow(10, (11.344 * (1 - 1 / A0))) - 1)
        SUM += 8.1328e-3 * (pow(10, (-3.49149 * (A0 - 1))) - 1)
        SUM += math.log(1013.246, 10)
        VP = pow(10, SUM - 3) * humidity
        Td = math.log(VP / 0.61078)
        Td = (241.88 * Td) / (17.558 - Td)
        return round(Td, 2)

    def computePunto_Di_Congelamento(self, temperature, humidity):
        """ https://pon.fr/dzvents-alerte-givre-et-calcul-humidite-absolue/ """
        punto_di_rugiada = self.computePunto_Di_Rugiada(temperature, humidity)
        T = temperature + 273.15
        Td = punto_di_rugiada + 273.15
        return round((Td + (2671.02 /((2954.61/T) + 2.193665 * math.log(T) - 13.3448))-T)-273.15,2)


    def toFahrenheit(self, celsius):
        """celsius to fahrenheit"""
        return 1.8 * celsius + 32.0

    def toCelsius(self, fahrenheit):
        """fahrenheit to celsius"""
        return (fahrenheit - 32.0) / 1.8

    def computeIndice_Di_Calore(self, temperature, humidity):
        """http://www.wpc.ncep.noaa.gov/html/heatindex_equation.shtml"""
        fahrenheit = self.toFahrenheit(temperature)
        hi = 0.5 * (fahrenheit + 61.0 + ((fahrenheit - 68.0) * 1.2) + (humidity * 0.094));

        if hi > 79:
            hi = -42.379 + 2.04901523 * fahrenheit
            hi = hi + 10.14333127 * humidity
            hi = hi + -0.22475541 * fahrenheit * humidity
            hi = hi + -0.00683783 * pow(fahrenheit, 2)
            hi = hi + -0.05481717 * pow(humidity, 2)
            hi = hi + 0.00122874 * pow(fahrenheit, 2) * humidity
            hi = hi + 0.00085282 * fahrenheit * pow(humidity, 2)
            hi = hi + -0.00000199 * pow(fahrenheit, 2) * pow(humidity, 2);

        if humidity < 13 and fahrenheit >= 80 and fahrenheit <= 112:
            hi = hi - ((13 - humidity) * 0.25) * math.sqrt((17 - abs(fahrenheit - 95)) * 0.05882)
        elif humidity > 85 and fahrenheit >= 80 and fahrenheit <= 87:
            hi = hi + ((humidity - 85) * 0.1) * ((87 - fahrenheit) * 0.2)

        return round(self.toCelsius(hi), 2)

    def computePercepita(self, temperature, humidity):
        """https://en.wikipedia.org/wiki/Dew_point"""
        punto_di_rugiada = self.computePunto_Di_Rugiada(temperature, humidity)
        if punto_di_rugiada < 10:
            return "Secco per alcuni"
        elif punto_di_rugiada < 13:
            return "Ottimale"
        elif punto_di_rugiada < 16:
            return "Confortevole"
        elif punto_di_rugiada < 18:
            return "Un po' umido"
        elif punto_di_rugiada < 21:
            return "Sgradevole per a maggior parte"
        elif punto_di_rugiada < 24:
            return "Fastidioso"
        elif punto_di_rugiada < 26:
            return "Estremamente fastidioso"
        return "Pericoloso per la salute"

    def computeRiskLevel(self, temperature, humidity):
        """ """
        thresholdUmidita_Assoluta = 2.8
        punto_di_rugiada = self.computePunto_Di_Rugiada(temperature, humidity)
        umidita_assoluta = self.computeUmidita_Assoluta(temperature, humidity)
        punto_di_congelamento = self.computePunto_Di_Congelamento(temperature, humidity)
        if temperature <= 1 and punto_di_congelamento <= 0 and umidita_assoluta < thresholdUmidita_Assoluta:
            return 1 # Ghiaccio improbabile nonostante la temperatura
        elif temperature <= 4 and punto_di_congelamento <= 0.5 and umidita_assoluta > thresholdUmidita_Assoluta:
            return 2 # Ghiaccio improbabile nonostante la temperatura
        elif temperature <= 1 and punto_di_congelamento <= 0 and umidita_assoluta > thresholdUmidita_Assoluta:
            return 3 # Presenza di ghiaccio
        return 0 # Nessun rischio di ghiaccio

    def computeUmidita_Assoluta(self, temperature, humidity):
        """https://carnotcycle.wordpress.com/2012/08/04/how-to-convert-relative-humidity-to-absolute-humidity/"""
        absTemperature = temperature + 273.15;
        absHumidity = 6.112;
        absHumidity *= math.exp((17.67 * temperature) / (243.5 + temperature));
        absHumidity *= humidity;
        absHumidity *= 2.1674;
        absHumidity /= absTemperature;
        return round(absHumidity, 2)

    """Sensor Properties"""
    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def device_state_attributes(self):
        """Return the state attributes."""
        return self._device_state_attributes

    @property
    def icon(self):
        """Return the icon to use in the frontend, if any."""
        return self._icon

    @property
    def device_class(self) -> Optional[str]:
        """Return the device class of the sensor."""
        return self._device_class

    @property
    def entity_picture(self):
        """Return the entity_picture to use in the frontend, if any."""
        return self._entity_picture

    @property
    def unit_of_measurement(self):
        """Return the unit_of_measurement of the device."""
        return self._unit_of_measurement

    @property
    def should_poll(self):
        """No polling needed."""
        return False

    async def async_update(self):
        """Update the state."""
        value = None
        if self._temperature and self._humidity:
            if self._sensor_type == "punto_di_rugiada":
                value = self.computePunto_Di_Rugiada(self._temperature, self._humidity)
            if self._sensor_type == "indice_di_calore":
                value = self.computeIndice_Di_Calore(self._temperature, self._humidity)
            elif self._sensor_type == "percepita":
                value = self.computePercepita(self._temperature, self._humidity)
            elif self._sensor_type == "umidita_assoluta":
                value = self.computeUmidita_Assoluta(self._temperature, self._humidity)
            elif self._sensor_type == "punto_di_congelamento":
                value = self.computePunto_Di_Congelamento(self._temperature, self._humidity)
##            elif self._sensor_type == "livello_di_rischio":
##                value = self.computeLivello_Di_Rischio(self._temperature, self._humidity)

        self._state = value
        self._device_state_attributes[ATTR_TEMPERATURE] = self._temperature
        self._device_state_attributes[ATTR_HUMIDITY] = self._humidity

        for property_name, template in (
                ('_icon', self._icon_template),
                ('_entity_picture', self._entity_picture_template)):
            if template is None:
                continue

            try:
                setattr(self, property_name, template.async_render())
            except TemplateError as ex:
                friendly_property_name = property_name[1:].replace('_', ' ')
                if ex.args and ex.args[0].startswith(
                        "UndefinedError: 'None' has no attribute"):
                    # Common during HA startup - so just a warning
                    _LOGGER.warning('Could not render %s template %s,'
                                    ' the state is unknown.',
                                    friendly_property_name, self._name)
                    continue

                try:
                    setattr(self, property_name,
                            getattr(super(), property_name))
                except AttributeError:
                    _LOGGER.error('Could not render %s template %s: %s',
                                  friendly_property_name, self._name, ex)

