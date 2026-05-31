#include <ch32v00x.h>
#include <debug.h>

#include "servo_config.h"

#define MODE_USES_ADC                                                          \
  ((TEST_MODE == TEST_MODE_ADC_ONLY) ||                                        \
   (TEST_MODE == TEST_MODE_MOTOR_SWEEP) ||                                     \
   (TEST_MODE == TEST_MODE_SERVO_CONTROL))
#define MODE_USES_MOTOR                                                        \
  ((TEST_MODE == TEST_MODE_MOTOR_SWEEP) ||                                     \
   (TEST_MODE == TEST_MODE_SERVO_CONTROL))
#define MODE_USES_RC_INPUT                                                     \
  ((TEST_MODE == TEST_MODE_RC_INPUT_CAPTURE) ||                                \
   (TEST_MODE == TEST_MODE_SERVO_CONTROL))
#define MODE_USES_PRINTF                                                       \
  ((TEST_MODE != TEST_MODE_SERVO_CONTROL) ||                                   \
   (SERVO_CONTROL_TELEMETRY_ENABLE != 0))
#define MODE_USES_SAMPLE_INDEX                                                 \
  ((TEST_MODE == TEST_MODE_ADC_ONLY) ||                                        \
   (TEST_MODE == TEST_MODE_MOTOR_SWEEP) ||                                     \
   ((TEST_MODE == TEST_MODE_SERVO_CONTROL) &&                                  \
    (SERVO_CONTROL_TELEMETRY_ENABLE != 0)))

typedef enum { SWEEP_TOWARD_LOW = 0, SWEEP_TOWARD_HIGH = 1 } SweepDirection;

typedef enum {
  MOTOR_PWM_COMMAND_COAST = 0,
  MOTOR_PWM_COMMAND_BRAKE = 1,
  MOTOR_PWM_COMMAND_TOWARD_HIGH = 2,
  MOTOR_PWM_COMMAND_TOWARD_LOW = 3,
} MotorPwmCommand;

void NMI_Handler(void) __attribute__((interrupt("WCH-Interrupt-fast")));
void HardFault_Handler(void) __attribute__((interrupt("WCH-Interrupt-fast")));
#if MODE_USES_RC_INPUT
void TIM1_CC_IRQHandler(void) __attribute__((interrupt("WCH-Interrupt-fast")));
#endif
#if MODE_USES_MOTOR
void TIM2_IRQHandler(void) __attribute__((interrupt("WCH-Interrupt-fast")));
#endif

#if MODE_USES_RC_INPUT
static uint16_t timer_delta_u16(uint16_t newer, uint16_t older) {
  return (uint16_t)(newer - older);
}

static uint16_t clamp_u16(uint16_t value, uint16_t low, uint16_t high) {
  if (value < low) {
    return low;
  }

  if (value > high) {
    return high;
  }

  return value;
}

static uint32_t abs_i32_to_u32(int32_t value) {
  return value < 0 ? (uint32_t)(-value) : (uint32_t)value;
}
#endif

#if TEST_MODE == TEST_MODE_SERVO_CONTROL
static int32_t clamp_i32(int32_t value, int32_t low, int32_t high) {
  if (value < low) {
    return low;
  }

  if (value > high) {
    return high;
  }

  return value;
}
#endif

#if MODE_USES_RC_INPUT
static volatile uint16_t rc_last_rising_capture_us = 0;
static volatile uint16_t rc_pulse_width_us = 0;
static volatile uint16_t rc_period_us = 0;
static volatile uint32_t rc_frame_count = 0;
static volatile uint8_t rc_have_rising_edge = 0;
static volatile uint8_t rc_waiting_for_falling_edge = 0;

static uint16_t clamp_pulse_us(uint16_t pulse_us) {
  return clamp_u16(pulse_us, RC_INPUT_MIN_US, RC_INPUT_MAX_US);
}

static int32_t rc_pulse_to_signed_angle_tenths(uint16_t pulse_us,
                                               int32_t full_scale_tenths) {
  int32_t clamped_pulse = (int32_t)clamp_pulse_us(pulse_us);
  return ((clamped_pulse - (int32_t)RC_INPUT_CENTER_US) * full_scale_tenths) /
         ((int32_t)RC_INPUT_MAX_US - (int32_t)RC_INPUT_CENTER_US);
}

static uint8_t rc_capture_is_valid(uint16_t pulse_us, uint16_t period_us) {
  return pulse_us >= RC_INPUT_VALID_MIN_US &&
         pulse_us <= RC_INPUT_VALID_MAX_US &&
         period_us >= RC_INPUT_PERIOD_VALID_MIN_US &&
         period_us <= RC_INPUT_PERIOD_VALID_MAX_US;
}

static void rc_capture_snapshot(uint32_t *frame_count, uint16_t *pulse_us,
                                uint16_t *period_us) {
  __disable_irq();
  *frame_count = rc_frame_count;
  *pulse_us = rc_pulse_width_us;
  *period_us = rc_period_us;
  __enable_irq();
}

static void rc_input_capture_init_pc4(void) {
  GPIO_InitTypeDef GPIO_InitStructure = {0};
  TIM_TimeBaseInitTypeDef TIM_TimeBaseStructure = {0};
  TIM_ICInitTypeDef TIM_ICInitStructure = {0};

  RCC_APB2PeriphClockCmd(
      RCC_APB2Periph_GPIOC | RCC_APB2Periph_AFIO | RCC_APB2Periph_TIM1, ENABLE);

  GPIO_PinRemapConfig(GPIO_PartialRemap2_TIM1, ENABLE);

  GPIO_InitStructure.GPIO_Pin = RC_INPUT_GPIO_PIN;
  GPIO_InitStructure.GPIO_Mode = GPIO_Mode_IN_FLOATING;
  GPIO_Init(RC_INPUT_GPIO_PORT, &GPIO_InitStructure);

  TIM_DeInit(TIM1);
  TIM_TimeBaseStructure.TIM_Period = 0xFFFF;
  TIM_TimeBaseStructure.TIM_Prescaler =
      (uint16_t)((SystemCoreClock / 1000000U) - 1U);
  TIM_TimeBaseStructure.TIM_ClockDivision = TIM_CKD_DIV1;
  TIM_TimeBaseStructure.TIM_CounterMode = TIM_CounterMode_Up;
  TIM_TimeBaseInit(TIM1, &TIM_TimeBaseStructure);

  TIM_ICInitStructure.TIM_Channel = TIM_Channel_4;
  TIM_ICInitStructure.TIM_ICPolarity = TIM_ICPolarity_Rising;
  TIM_ICInitStructure.TIM_ICSelection = TIM_ICSelection_DirectTI;
  TIM_ICInitStructure.TIM_ICPrescaler = TIM_ICPSC_DIV1;
  TIM_ICInitStructure.TIM_ICFilter = 0x03;
  TIM_ICInit(TIM1, &TIM_ICInitStructure);

  TIM_ClearITPendingBit(TIM1, TIM_IT_CC4);
  TIM_ITConfig(TIM1, TIM_IT_CC4, ENABLE);
  NVIC_EnableIRQ(TIM1_CC_IRQn);
  TIM_Cmd(TIM1, ENABLE);
  __enable_irq();
}
#endif

#if MODE_USES_ADC
static void adc_init_pa2_a0(void) {
  GPIO_InitTypeDef GPIO_InitStructure = {0};
  ADC_InitTypeDef ADC_InitStructure = {0};

  RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOA | RCC_APB2Periph_ADC1, ENABLE);
  RCC_ADCCLKConfig(RCC_PCLK2_Div8);

  GPIO_InitStructure.GPIO_Pin = ADC_INPUT_GPIO_PIN;
  GPIO_InitStructure.GPIO_Mode = GPIO_Mode_AIN;
  GPIO_Init(ADC_INPUT_GPIO_PORT, &GPIO_InitStructure);

  ADC_DeInit(ADC1);
  ADC_InitStructure.ADC_Mode = ADC_Mode_Independent;
  ADC_InitStructure.ADC_ScanConvMode = DISABLE;
  ADC_InitStructure.ADC_ContinuousConvMode = DISABLE;
  ADC_InitStructure.ADC_ExternalTrigConv = ADC_ExternalTrigConv_None;
  ADC_InitStructure.ADC_DataAlign = ADC_DataAlign_Right;
  ADC_InitStructure.ADC_NbrOfChannel = 1;
  ADC_Init(ADC1, &ADC_InitStructure);

  ADC_RegularChannelConfig(ADC1, ADC_INPUT_CHANNEL, 1,
                           ADC_SampleTime_241Cycles);
  ADC_Cmd(ADC1, ENABLE);

  ADC_ResetCalibration(ADC1);
  while (ADC_GetResetCalibrationStatus(ADC1) == SET) {
  }

  ADC_StartCalibration(ADC1);
  while (ADC_GetCalibrationStatus(ADC1) == SET) {
  }
}

static uint16_t adc_read_raw(void) {
  ADC_ClearFlag(ADC1, ADC_FLAG_EOC);
  ADC_SoftwareStartConvCmd(ADC1, ENABLE);

  while (ADC_GetFlagStatus(ADC1, ADC_FLAG_EOC) == RESET) {
  }

  return ADC_GetConversionValue(ADC1) & ADC_FULL_SCALE_COUNTS;
}

static uint16_t adc_read_average(uint8_t samples) {
  uint32_t sum = 0;

  for (uint8_t i = 0; i < samples; i++) {
    sum += adc_read_raw();
  }

  return (uint16_t)((sum + (samples / 2U)) / samples);
}

#if TEST_MODE != TEST_MODE_SERVO_CONTROL
static uint32_t adc_to_pot_angle_tenths(uint16_t adc_count) {
  return ((uint32_t)adc_count * ANGLE_FULL_SCALE_DEGREES * 10U +
          (ADC_FULL_SCALE_COUNTS / 2U)) /
         ADC_FULL_SCALE_COUNTS;
}
#endif

#if TEST_MODE == TEST_MODE_SERVO_CONTROL
static int32_t adc_to_servo_angle_tenths(uint16_t adc_count) {
  int32_t adc = (int32_t)adc_count;
  int32_t center = (int32_t)POT_ADC_AT_CENTER;

  if (adc >= center) {
    int32_t span = (int32_t)POT_ADC_AT_POS160 - center;
    int32_t angle =
        ((adc - center) * SERVO_ANGLE_FULL_SCALE_TENTHS + (span / 2)) / span;
    return clamp_i32(angle, 0, SERVO_ANGLE_FULL_SCALE_TENTHS);
  }

  int32_t span = center - (int32_t)POT_ADC_AT_NEG160;
  int32_t angle =
      ((center - adc) * SERVO_ANGLE_FULL_SCALE_TENTHS + (span / 2)) / span;
  return -clamp_i32(angle, 0, SERVO_ANGLE_FULL_SCALE_TENTHS);
}

static int32_t compensate_command_angle_tenths(int32_t command_tenths) {
  int32_t rounding = command_tenths >= 0 ? 500 : -500;
  int32_t compensated =
      ((command_tenths * SERVO_COMMAND_GAIN_PERMILLE) + rounding) / 1000 +
      SERVO_COMMAND_OFFSET_TENTHS;

#if SERVO_ENDPOINT_PROTECTION_ENABLE
  int32_t limit_tenths = (int32_t)SERVO_ENDPOINT_LIMIT_TENTHS;
  limit_tenths =
      clamp_i32(limit_tenths, 0, (int32_t)SERVO_ANGLE_FULL_SCALE_TENTHS);
  return clamp_i32(compensated, -limit_tenths, limit_tenths);
#else
  return clamp_i32(compensated, -SERVO_ANGLE_FULL_SCALE_TENTHS,
                   SERVO_ANGLE_FULL_SCALE_TENTHS);
#endif
}
#endif
#endif

#if MODE_USES_MOTOR
static volatile MotorPwmCommand motor_pwm_command = MOTOR_PWM_COMMAND_COAST;
static volatile uint16_t motor_pwm_duty_ticks = 0;

static uint16_t motor_pwm_duty_to_ticks(uint16_t duty) {
  uint32_t ticks;

  if (duty >= MOTOR_PWM_DUTY_MAX) {
    return MOTOR_PWM_PERIOD_TICKS;
  }

  if (duty == 0U) {
    return 0U;
  }

  ticks =
      ((uint32_t)duty * MOTOR_PWM_PERIOD_TICKS + (MOTOR_PWM_DUTY_MAX / 2U)) /
      MOTOR_PWM_DUTY_MAX;
  if (ticks == 0U) {
    ticks = 1U;
  }

  return (uint16_t)ticks;
}

static void motor_pwm_apply_period_start(MotorPwmCommand command,
                                         uint16_t duty_ticks) {
  if (command == MOTOR_PWM_COMMAND_BRAKE) {
    GPIO_SetBits(MOTOR_GPIO_PORT, MOTOR_GPIO_PINS);
    return;
  }

  GPIO_ResetBits(MOTOR_GPIO_PORT, MOTOR_GPIO_PINS);

  if (duty_ticks == 0U) {
    return;
  }

  if (command == MOTOR_PWM_COMMAND_TOWARD_HIGH) {
    GPIO_SetBits(MOTOR_GPIO_PORT, MOTOR_TOWARD_HIGH_PIN);
  } else if (command == MOTOR_PWM_COMMAND_TOWARD_LOW) {
    GPIO_SetBits(MOTOR_GPIO_PORT, MOTOR_TOWARD_LOW_PIN);
  }
}

static void motor_pwm_init(void) {
  GPIO_InitTypeDef GPIO_InitStructure = {0};
  TIM_TimeBaseInitTypeDef TIM_TimeBaseStructure = {0};
  TIM_OCInitTypeDef TIM_OCInitStructure = {0};

  RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOC, ENABLE);
  RCC_APB1PeriphClockCmd(RCC_APB1Periph_TIM2, ENABLE);

  GPIO_InitStructure.GPIO_Pin = MOTOR_GPIO_PINS;
  GPIO_InitStructure.GPIO_Mode = GPIO_Mode_Out_PP;
  GPIO_InitStructure.GPIO_Speed = GPIO_Speed_30MHz;
  GPIO_Init(MOTOR_GPIO_PORT, &GPIO_InitStructure);
  GPIO_ResetBits(MOTOR_GPIO_PORT, MOTOR_GPIO_PINS);

  TIM_DeInit(TIM2);
  TIM_TimeBaseStructure.TIM_Period = (uint16_t)(MOTOR_PWM_PERIOD_TICKS - 1U);
  TIM_TimeBaseStructure.TIM_Prescaler =
      (uint16_t)((SystemCoreClock / MOTOR_PWM_TIMER_HZ) - 1U);
  TIM_TimeBaseStructure.TIM_ClockDivision = TIM_CKD_DIV1;
  TIM_TimeBaseStructure.TIM_CounterMode = TIM_CounterMode_Up;
  TIM_TimeBaseInit(TIM2, &TIM_TimeBaseStructure);

  TIM_OCInitStructure.TIM_OCMode = TIM_OCMode_Timing;
  TIM_OCInitStructure.TIM_OutputState = TIM_OutputState_Disable;
  TIM_OCInitStructure.TIM_Pulse = 0;
  TIM_OCInitStructure.TIM_OCPolarity = TIM_OCPolarity_High;
  TIM_OC1Init(TIM2, &TIM_OCInitStructure);

  TIM_ClearITPendingBit(TIM2, TIM_IT_Update | TIM_IT_CC1);
  TIM_ITConfig(TIM2, TIM_IT_Update | TIM_IT_CC1, ENABLE);
  NVIC_EnableIRQ(TIM2_IRQn);
  TIM_Cmd(TIM2, ENABLE);
  __enable_irq();
}

static void motor_pwm_set(MotorPwmCommand command, uint16_t duty) {
  uint16_t duty_ticks;

  if (command == MOTOR_PWM_COMMAND_COAST) {
    duty = 0U;
  } else if (command == MOTOR_PWM_COMMAND_BRAKE) {
    duty = MOTOR_PWM_DUTY_MAX;
  } else if (duty > MOTOR_PWM_DUTY_MAX) {
    duty = MOTOR_PWM_DUTY_MAX;
  }

  duty_ticks = motor_pwm_duty_to_ticks(duty);

  __disable_irq();
  motor_pwm_duty_ticks = duty_ticks;
  motor_pwm_command = command;
  TIM_SetCompare1(TIM2, duty_ticks);
  motor_pwm_apply_period_start(command, duty_ticks);
  __enable_irq();
}

static void motor_pwm_coast(void) {
  motor_pwm_set(MOTOR_PWM_COMMAND_COAST, 0U);
}

static void motor_pwm_brake(void) {
  motor_pwm_set(MOTOR_PWM_COMMAND_BRAKE, MOTOR_PWM_DUTY_MAX);
}

static void motor_pwm_drive_toward_high(uint16_t duty) {
  motor_pwm_set(MOTOR_PWM_COMMAND_TOWARD_HIGH, duty);
}

static void motor_pwm_drive_toward_low(uint16_t duty) {
  motor_pwm_set(MOTOR_PWM_COMMAND_TOWARD_LOW, duty);
}

#if TEST_MODE == TEST_MODE_SERVO_CONTROL
static uint16_t control_duty_from_error(uint32_t abs_error_tenths) {
  uint32_t duty;

  if (abs_error_tenths <= CONTROL_POSITION_DEADBAND_TENTHS) {
    return 0U;
  }

  if (abs_error_tenths >= CONTROL_SLOW_ZONE_TENTHS) {
    return MOTOR_PWM_DUTY_MAX;
  }

  duty = MOTOR_PWM_MIN_DUTY +
         ((abs_error_tenths - CONTROL_POSITION_DEADBAND_TENTHS) *
          (MOTOR_PWM_DUTY_MAX - MOTOR_PWM_MIN_DUTY)) /
             (CONTROL_SLOW_ZONE_TENTHS - CONTROL_POSITION_DEADBAND_TENTHS);
  return (uint16_t)clamp_u16((uint16_t)duty, MOTOR_PWM_MIN_DUTY,
                             MOTOR_PWM_DUTY_MAX);
}
#endif
#endif

int main(void) {
#if MODE_USES_SAMPLE_INDEX
  uint32_t sample_index = 0;
#endif

#if TEST_MODE == TEST_MODE_MOTOR_SWEEP
  uint32_t direction_changes = 0;
  SweepDirection sweep_direction = SWEEP_TOWARD_LOW;
  uint8_t endpoint_armed = 1;
  uint32_t sweep_midpoint_tenths =
      (SWEEP_LOW_TARGET_TENTHS + SWEEP_HIGH_TARGET_TENTHS) / 2U;
#endif

#if TEST_MODE == TEST_MODE_SERVO_CONTROL
  int32_t target_angle_tenths = 0;
  int8_t last_drive_direction = 0;
  uint32_t last_rc_frame_count = 0;
  uint16_t rc_stale_loops =
      (uint16_t)(RC_INPUT_TIMEOUT_MS / CONTROL_LOOP_INTERVAL_MS);
#if SERVO_CONTROL_TELEMETRY_ENABLE
  uint16_t debug_elapsed_ms = CONTROL_DEBUG_INTERVAL_MS;
#endif
#endif

  SystemCoreClockUpdate();
  Delay_Init();

#if MODE_USES_PRINTF
#if (SDI_PRINT == SDI_PR_OPEN)
  SDI_Printf_Enable();
#else
  USART_Printf_Init(UART_BAUD_RATE);
#endif
#endif

#if MODE_USES_ADC
  adc_init_pa2_a0();
#endif

#if MODE_USES_RC_INPUT
  rc_input_capture_init_pc4();
#endif

#if MODE_USES_MOTOR
  motor_pwm_init();
  motor_pwm_coast();
#endif

#if TEST_MODE == TEST_MODE_RC_INPUT_CAPTURE
  printf("frame,pulse_us,period_us,freq_hz,valid,sg90_deg,n20_deg\r\n");
#elif TEST_MODE == TEST_MODE_SERVO_CONTROL && SERVO_CONTROL_TELEMETRY_ENABLE
  printf("sample,target_deg,angle_deg,error_deg,duty,pulse_us,valid\r\n");
#endif

#if TEST_MODE == TEST_MODE_MOTOR_SWEEP
  uint32_t startup_angle_tenths =
      adc_to_pot_angle_tenths(adc_read_average(ADC_AVERAGE_SAMPLES));
  sweep_direction = (startup_angle_tenths < sweep_midpoint_tenths)
                        ? SWEEP_TOWARD_HIGH
                        : SWEEP_TOWARD_LOW;
#endif

  while (1) {
#if TEST_MODE == TEST_MODE_RC_INPUT_CAPTURE
    uint32_t frame_count;
    uint16_t pulse_us;
    uint16_t period_us;
    uint32_t freq_tenths;
    uint8_t valid;
    int32_t sg90_angle_tenths;
    int32_t n20_angle_tenths;
    uint32_t sg90_abs_tenths;
    uint32_t n20_abs_tenths;

    rc_capture_snapshot(&frame_count, &pulse_us, &period_us);
    freq_tenths = period_us > 0U ? (10000000UL / period_us) : 0U;
    valid = rc_capture_is_valid(pulse_us, period_us);
    sg90_angle_tenths =
        rc_pulse_to_signed_angle_tenths(pulse_us, RC_SG90_FULL_SCALE_TENTHS);
    n20_angle_tenths =
        rc_pulse_to_signed_angle_tenths(pulse_us, RC_N20_FULL_SCALE_TENTHS);
    sg90_abs_tenths = abs_i32_to_u32(sg90_angle_tenths);
    n20_abs_tenths = abs_i32_to_u32(n20_angle_tenths);

    printf("%lu,%u,%u,%lu.%lu,%u,%c%lu.%lu,%c%lu.%lu\r\n", frame_count,
           pulse_us, period_us, freq_tenths / 10U, freq_tenths % 10U, valid,
           sg90_angle_tenths < 0 ? '-' : '+', sg90_abs_tenths / 10U,
           sg90_abs_tenths % 10U, n20_angle_tenths < 0 ? '-' : '+',
           n20_abs_tenths / 10U, n20_abs_tenths % 10U);

    Delay_Ms(RC_INPUT_REPORT_INTERVAL_MS);
#elif TEST_MODE == TEST_MODE_SERVO_CONTROL
    uint32_t frame_count;
    uint16_t pulse_us;
    uint16_t period_us;
    uint16_t average;
    uint8_t signal_valid;
    int32_t measured_angle_tenths;
    int32_t error_tenths;
    uint32_t abs_error_tenths;
    uint16_t duty = 0;

    rc_capture_snapshot(&frame_count, &pulse_us, &period_us);
    if (frame_count != last_rc_frame_count) {
      last_rc_frame_count = frame_count;
      rc_stale_loops = 0;
    } else if (rc_stale_loops <
               (uint16_t)(RC_INPUT_TIMEOUT_MS / CONTROL_LOOP_INTERVAL_MS +
                          1U)) {
      rc_stale_loops++;
    }

    signal_valid = rc_capture_is_valid(pulse_us, period_us) &&
                   rc_stale_loops <= (uint16_t)(RC_INPUT_TIMEOUT_MS /
                                                CONTROL_LOOP_INTERVAL_MS);
    if (signal_valid != 0U) {
      int32_t command_angle_tenths = rc_pulse_to_signed_angle_tenths(
          pulse_us, SERVO_ANGLE_FULL_SCALE_TENTHS);
      target_angle_tenths =
          compensate_command_angle_tenths(command_angle_tenths);
    }

    average = adc_read_average(ADC_CONTROL_SAMPLES);
    measured_angle_tenths = adc_to_servo_angle_tenths(average);
    error_tenths = target_angle_tenths - measured_angle_tenths;
    abs_error_tenths = abs_i32_to_u32(error_tenths);

    if (signal_valid == 0U) {
      motor_pwm_coast();
      last_drive_direction = 0;
    } else if (abs_error_tenths <= CONTROL_POSITION_DEADBAND_TENTHS) {
#if CONTROL_HOLD_BRAKE_ENABLED
      motor_pwm_brake();
#else
      motor_pwm_coast();
#endif
      last_drive_direction = 0;
    } else {
      int8_t requested_direction = error_tenths > 0 ? 1 : -1;

      if (last_drive_direction != 0 &&
          requested_direction != last_drive_direction &&
          abs_error_tenths < CONTROL_REVERSE_DEADBAND_TENTHS) {
        motor_pwm_brake();
      } else {
        duty = control_duty_from_error(abs_error_tenths);
        if (requested_direction > 0) {
          motor_pwm_drive_toward_high(duty);
        } else {
          motor_pwm_drive_toward_low(duty);
        }
        last_drive_direction = requested_direction;
      }
    }

#if SERVO_CONTROL_TELEMETRY_ENABLE
    if (debug_elapsed_ms >= CONTROL_DEBUG_INTERVAL_MS) {
      uint32_t target_abs_tenths = abs_i32_to_u32(target_angle_tenths);
      uint32_t measured_abs_tenths = abs_i32_to_u32(measured_angle_tenths);
      uint32_t error_abs_tenths = abs_i32_to_u32(error_tenths);

      printf("%lu,%c%lu.%lu,%c%lu.%lu,%c%lu.%lu,%u,%u,%u\r\n", sample_index++,
             target_angle_tenths < 0 ? '-' : '+', target_abs_tenths / 10U,
             target_abs_tenths % 10U, measured_angle_tenths < 0 ? '-' : '+',
             measured_abs_tenths / 10U, measured_abs_tenths % 10U,
             error_tenths < 0 ? '-' : '+', error_abs_tenths / 10U,
             error_abs_tenths % 10U, duty, pulse_us, signal_valid);
      debug_elapsed_ms = 0;
    }

    debug_elapsed_ms += CONTROL_LOOP_INTERVAL_MS;
#endif
    Delay_Ms(CONTROL_LOOP_INTERVAL_MS);
#else
    uint16_t raw = adc_read_raw();
    uint16_t average = adc_read_average(ADC_AVERAGE_SAMPLES);
    uint32_t millivolts =
        ((uint32_t)average * ADC_REFERENCE_MV + (ADC_FULL_SCALE_COUNTS / 2U)) /
        ADC_FULL_SCALE_COUNTS;
    uint32_t percent_tenths =
        ((uint32_t)average * 1000U + (ADC_FULL_SCALE_COUNTS / 2U)) /
        ADC_FULL_SCALE_COUNTS;
    uint32_t angle_tenths = adc_to_pot_angle_tenths(average);

#if TEST_MODE == TEST_MODE_MOTOR_SWEEP
    if (sweep_direction == SWEEP_TOWARD_HIGH) {
      if (angle_tenths < sweep_midpoint_tenths) {
        endpoint_armed = 1;
      }

      if (endpoint_armed && angle_tenths >= (SWEEP_HIGH_TARGET_TENTHS -
                                             SWEEP_TARGET_TOLERANCE_TENTHS)) {
        motor_pwm_brake();
        Delay_Ms(MOTOR_REVERSE_BRAKE_MS);
        motor_pwm_coast();
        Delay_Ms(SWEEP_ENDPOINT_SETTLE_MS);
        sweep_direction = SWEEP_TOWARD_LOW;
        endpoint_armed = 0;
        direction_changes++;
        motor_pwm_drive_toward_low(MOTOR_PWM_DUTY_MAX);
      } else {
        motor_pwm_drive_toward_high(MOTOR_PWM_DUTY_MAX);
      }
    } else {
      if (angle_tenths > sweep_midpoint_tenths) {
        endpoint_armed = 1;
      }

      if (endpoint_armed && angle_tenths <= (SWEEP_LOW_TARGET_TENTHS +
                                             SWEEP_TARGET_TOLERANCE_TENTHS)) {
        motor_pwm_brake();
        Delay_Ms(MOTOR_REVERSE_BRAKE_MS);
        motor_pwm_coast();
        Delay_Ms(SWEEP_ENDPOINT_SETTLE_MS);
        sweep_direction = SWEEP_TOWARD_HIGH;
        endpoint_armed = 0;
        direction_changes++;
        motor_pwm_drive_toward_high(MOTOR_PWM_DUTY_MAX);
      } else {
        motor_pwm_drive_toward_low(MOTOR_PWM_DUTY_MAX);
      }
    }
#endif

    printf("%lu,%u,%u,%lu,%lu.%lu,%lu.%lu", sample_index++, raw, average,
           millivolts, percent_tenths / 10U, percent_tenths % 10U,
           angle_tenths / 10U, angle_tenths % 10U);
#if TEST_MODE == TEST_MODE_MOTOR_SWEEP
    printf(",%lu", direction_changes);
#else
    printf(",0");
#endif
    printf("\r\n");

    Delay_Ms(ADC_UPDATE_INTERVAL_MS);
#endif
  }

  return 0;
}

void NMI_Handler(void) {}
void HardFault_Handler(void) {
  while (1) {
  }
}

#if MODE_USES_RC_INPUT
void TIM1_CC_IRQHandler(void) {
  if (TIM_GetITStatus(TIM1, TIM_IT_CC4) != RESET) {
    uint16_t capture_us = TIM_GetCapture4(TIM1);
    TIM_ClearITPendingBit(TIM1, TIM_IT_CC4);

    if (rc_waiting_for_falling_edge == 0U) {
      if (rc_have_rising_edge != 0U) {
        rc_period_us = timer_delta_u16(capture_us, rc_last_rising_capture_us);
      }

      rc_last_rising_capture_us = capture_us;
      rc_have_rising_edge = 1U;
      rc_waiting_for_falling_edge = 1U;
      TIM_OC4PolarityConfig(TIM1, TIM_ICPolarity_Falling);
    } else {
      rc_pulse_width_us =
          timer_delta_u16(capture_us, rc_last_rising_capture_us);
      rc_frame_count++;
      rc_waiting_for_falling_edge = 0U;
      TIM_OC4PolarityConfig(TIM1, TIM_ICPolarity_Rising);
    }
  }
}
#endif

#if MODE_USES_MOTOR
void TIM2_IRQHandler(void) {
  if (TIM_GetITStatus(TIM2, TIM_IT_Update) != RESET) {
    MotorPwmCommand command = motor_pwm_command;
    uint16_t duty_ticks = motor_pwm_duty_ticks;

    TIM_ClearITPendingBit(TIM2, TIM_IT_Update);
    TIM_SetCompare1(TIM2, duty_ticks);
    motor_pwm_apply_period_start(command, duty_ticks);
  }

  if (TIM_GetITStatus(TIM2, TIM_IT_CC1) != RESET) {
    MotorPwmCommand command = motor_pwm_command;
    uint16_t duty_ticks = motor_pwm_duty_ticks;

    TIM_ClearITPendingBit(TIM2, TIM_IT_CC1);
    if ((command == MOTOR_PWM_COMMAND_TOWARD_HIGH ||
         command == MOTOR_PWM_COMMAND_TOWARD_LOW) &&
        duty_ticks > 0U && duty_ticks < MOTOR_PWM_PERIOD_TICKS) {
      GPIO_ResetBits(MOTOR_GPIO_PORT, MOTOR_GPIO_PINS);
    }
  }
}
#endif
