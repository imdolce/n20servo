#ifndef SERVO_CONFIG_H
#define SERVO_CONFIG_H

#include <ch32v00x.h>

/*
 * User configuration for the N20 servo firmware.
 *
 * Angle values ending in _TENTHS are in 0.1 degree units:
 *   1500 = 150.0 degrees
 *   12   = 1.2 degrees
 */

/* ADC input GPIO port for the potentiometer wiper. */
#ifndef ADC_INPUT_GPIO_PORT
#define ADC_INPUT_GPIO_PORT GPIOA
#endif

/* ADC input GPIO pin for the potentiometer wiper. PA2 is ADC channel A0. */
#ifndef ADC_INPUT_GPIO_PIN
#define ADC_INPUT_GPIO_PIN GPIO_Pin_2
#endif

/* ADC regular channel matching ADC_INPUT_GPIO_PIN. PA2 uses ADC_Channel_0. */
#ifndef ADC_INPUT_CHANNEL
#define ADC_INPUT_CHANNEL ADC_Channel_0
#endif

/* Number of ADC samples used for diagnostic averaging. */
#ifndef ADC_AVERAGE_SAMPLES
#define ADC_AVERAGE_SAMPLES 16U
#endif

/* Number of ADC samples used per closed-loop control update. */
#ifndef ADC_CONTROL_SAMPLES
#define ADC_CONTROL_SAMPLES 4U
#endif

/* Maximum 10-bit ADC count from the CH32V003 ADC. */
#ifndef ADC_FULL_SCALE_COUNTS
#define ADC_FULL_SCALE_COUNTS 1023U
#endif

/* ADC reference voltage in millivolts for debug output calculations. */
#ifndef ADC_REFERENCE_MV
#define ADC_REFERENCE_MV 5000U
#endif

/* Delay between ADC-only or motor-sweep debug rows. */
#ifndef ADC_UPDATE_INTERVAL_MS
#define ADC_UPDATE_INTERVAL_MS 10U
#endif

/* Full potentiometer travel used by ADC-only angle display. */
#ifndef ANGLE_FULL_SCALE_DEGREES
#define ANGLE_FULL_SCALE_DEGREES 330U
#endif

/* UART baud rate for printf when SDI_PRINT is disabled. */
#ifndef UART_BAUD_RATE
#define UART_BAUD_RATE 921600U
#endif

/* ADC-only mode: read the potentiometer and print ADC/angle data. */
#define TEST_MODE_ADC_ONLY 0U

/* Motor sweep mode: drive between configured sweep endpoints. */
#define TEST_MODE_MOTOR_SWEEP 1U

/* Backward-compatible name for the motor sweep test mode. */
#define TEST_MODE_MOTOR_AND_ADC TEST_MODE_MOTOR_SWEEP

/* RC input-capture mode: measure incoming 50 Hz servo PWM only. */
#define TEST_MODE_RC_INPUT_CAPTURE 2U

/* Closed-loop servo mode: capture RC input and control motor position. */
#define TEST_MODE_SERVO_CONTROL 3U

/* Default firmware mode when platformio.ini does not override TEST_MODE. */
#ifndef TEST_MODE
#define TEST_MODE TEST_MODE_SERVO_CONTROL
#endif

/* Enable CSV telemetry in closed-loop mode. Keep off for lowest loop jitter. */
#ifndef SERVO_CONTROL_TELEMETRY_ENABLE
#define SERVO_CONTROL_TELEMETRY_ENABLE 0
#endif

/* GPIO port for the incoming 50 Hz RC servo PWM signal. */
#ifndef RC_INPUT_GPIO_PORT
#define RC_INPUT_GPIO_PORT GPIOC
#endif

/* GPIO pin for the incoming 50 Hz RC servo PWM signal. PC4 uses TIM1_CH4. */
#ifndef RC_INPUT_GPIO_PIN
#define RC_INPUT_GPIO_PIN GPIO_Pin_4
#endif

/* Pulse width mapped to full negative command. */
#ifndef RC_INPUT_MIN_US
#define RC_INPUT_MIN_US 1000U
#endif

/* Pulse width mapped to center command. */
#ifndef RC_INPUT_CENTER_US
#define RC_INPUT_CENTER_US 1500U
#endif

/* Pulse width mapped to full positive command. */
#ifndef RC_INPUT_MAX_US
#define RC_INPUT_MAX_US 2000U
#endif

/* Lowest pulse width accepted as a valid input-capture signal. */
#ifndef RC_INPUT_VALID_MIN_US
#define RC_INPUT_VALID_MIN_US 750U
#endif

/* Highest pulse width accepted as a valid input-capture signal. */
#ifndef RC_INPUT_VALID_MAX_US
#define RC_INPUT_VALID_MAX_US 2250U
#endif

/* Lowest accepted RC frame period. 15000 us is about 66 Hz. */
#ifndef RC_INPUT_PERIOD_VALID_MIN_US
#define RC_INPUT_PERIOD_VALID_MIN_US 15000U
#endif

/* Highest accepted RC frame period. 25000 us is 40 Hz. */
#ifndef RC_INPUT_PERIOD_VALID_MAX_US
#define RC_INPUT_PERIOD_VALID_MAX_US 25000U
#endif

/* Delay between rows in RC input-capture diagnostic mode. */
#ifndef RC_INPUT_REPORT_INTERVAL_MS
#define RC_INPUT_REPORT_INTERVAL_MS 100U
#endif

/* Time without a fresh RC frame before closed-loop mode coasts the motor. */
#ifndef RC_INPUT_TIMEOUT_MS
#define RC_INPUT_TIMEOUT_MS 100U
#endif

/* Reference SG90-style command range shown in input-capture diagnostics. */
#ifndef RC_SG90_FULL_SCALE_TENTHS
#define RC_SG90_FULL_SCALE_TENTHS 900
#endif

/* N20 servo command range shown in input-capture diagnostics. */
#ifndef RC_N20_FULL_SCALE_TENTHS
#define RC_N20_FULL_SCALE_TENTHS 1500
#endif

/* Absolute measured servo range used by the feedback potentiometer mapping. */
#ifndef SERVO_ANGLE_FULL_SCALE_TENTHS
#define SERVO_ANGLE_FULL_SCALE_TENTHS 1600
#endif

/* ADC count measured at the negative mechanical endpoint. */
#ifndef POT_ADC_AT_NEG160
#define POT_ADC_AT_NEG160 47U
#endif

/* ADC count measured at the center position. */
#ifndef POT_ADC_AT_CENTER
#define POT_ADC_AT_CENTER 512U
#endif

/* ADC count measured at the positive mechanical endpoint. */
#ifndef POT_ADC_AT_POS160
#define POT_ADC_AT_POS160 977U
#endif

/* Command gain trim in permille. 1000 means no scale correction. */
#ifndef SERVO_COMMAND_GAIN_PERMILLE
#define SERVO_COMMAND_GAIN_PERMILLE 1062
#endif

/* Command offset trim in 0.1 degree units. Applied after gain. */
#ifndef SERVO_COMMAND_OFFSET_TENTHS
#define SERVO_COMMAND_OFFSET_TENTHS 0
#endif

/* Clamp commanded endpoints below the physical range to avoid dead zones. */
#ifndef SERVO_ENDPOINT_PROTECTION_ENABLE
#define SERVO_ENDPOINT_PROTECTION_ENABLE 1U
#endif

/* Command clamp used when endpoint protection is enabled. */
#ifndef SERVO_ENDPOINT_LIMIT_TENTHS
#define SERVO_ENDPOINT_LIMIT_TENTHS 1500
#endif

/* Closed-loop update interval. 2 ms gives a 500 Hz control loop. */
#ifndef CONTROL_LOOP_INTERVAL_MS
#define CONTROL_LOOP_INTERVAL_MS 2U
#endif

/* Delay between telemetry rows when closed-loop telemetry is enabled. */
#ifndef CONTROL_DEBUG_INTERVAL_MS
#define CONTROL_DEBUG_INTERVAL_MS 50U
#endif

/* Position error band where the controller stops driving the motor. */
#ifndef CONTROL_POSITION_DEADBAND_TENTHS
#define CONTROL_POSITION_DEADBAND_TENTHS 12U
#endif

/* Small-error direction reversal band where the controller brakes first. */
#ifndef CONTROL_REVERSE_DEADBAND_TENTHS
#define CONTROL_REVERSE_DEADBAND_TENTHS 30U
#endif

/* Error size where drive reaches full duty; below this it ramps down. */
#ifndef CONTROL_SLOW_ZONE_TENTHS
#define CONTROL_SLOW_ZONE_TENTHS 250U
#endif

/* Hold with H-bridge brake inside deadband instead of coasting. */
#ifndef CONTROL_HOLD_BRAKE_ENABLED
#define CONTROL_HOLD_BRAKE_ENABLED 1U
#endif

/* GPIO PWM frequency for the two H-bridge input pins. */
#ifndef MOTOR_PWM_HZ
#define MOTOR_PWM_HZ 2000U
#endif

/* Timer tick rate used to generate the GPIO PWM waveform. */
#ifndef MOTOR_PWM_TIMER_HZ
#define MOTOR_PWM_TIMER_HZ 1000000U
#endif

/* Timer period ticks derived from MOTOR_PWM_TIMER_HZ and MOTOR_PWM_HZ. */
#ifndef MOTOR_PWM_PERIOD_TICKS
#define MOTOR_PWM_PERIOD_TICKS (MOTOR_PWM_TIMER_HZ / MOTOR_PWM_HZ)
#endif

/* Maximum motor duty command. 1000 represents 100.0 percent. */
#ifndef MOTOR_PWM_DUTY_MAX
#define MOTOR_PWM_DUTY_MAX 1000U
#endif

/* Minimum duty used once outside the position deadband. */
#ifndef MOTOR_PWM_MIN_DUTY
#define MOTOR_PWM_MIN_DUTY 220U
#endif

/* Brake time before reversing direction in sweep mode. */
#ifndef MOTOR_REVERSE_BRAKE_MS
#define MOTOR_REVERSE_BRAKE_MS 50U
#endif

/* Pause after each completed endpoint in sweep test mode. */
#ifndef SWEEP_ENDPOINT_SETTLE_MS
#define SWEEP_ENDPOINT_SETTLE_MS 3000U
#endif

/* Low endpoint target for motor sweep test mode. */
#ifndef SWEEP_LOW_TARGET_TENTHS
#define SWEEP_LOW_TARGET_TENTHS 10U
#endif

/* High endpoint target for motor sweep test mode. */
#ifndef SWEEP_HIGH_TARGET_TENTHS
#define SWEEP_HIGH_TARGET_TENTHS 3300U
#endif

/* Sweep endpoint tolerance used before changing direction. */
#ifndef SWEEP_TARGET_TOLERANCE_TENTHS
#define SWEEP_TARGET_TOLERANCE_TENTHS 10U
#endif

/* GPIO port for both H-bridge control pins. */
#ifndef MOTOR_GPIO_PORT
#define MOTOR_GPIO_PORT GPIOC
#endif

/* First H-bridge control pin. */
#ifndef MOTOR_PC1_PIN
#define MOTOR_PC1_PIN GPIO_Pin_1
#endif

/* Second H-bridge control pin. */
#ifndef MOTOR_PC2_PIN
#define MOTOR_PC2_PIN GPIO_Pin_2
#endif

/* Combined H-bridge pin mask. */
#ifndef MOTOR_GPIO_PINS
#define MOTOR_GPIO_PINS (MOTOR_PC1_PIN | MOTOR_PC2_PIN)
#endif

/* H-bridge pin that increases the measured potentiometer angle. */
#ifndef MOTOR_TOWARD_HIGH_PIN
#define MOTOR_TOWARD_HIGH_PIN MOTOR_PC2_PIN
#endif

/* H-bridge pin that decreases the measured potentiometer angle. */
#ifndef MOTOR_TOWARD_LOW_PIN
#define MOTOR_TOWARD_LOW_PIN MOTOR_PC1_PIN
#endif

#endif
