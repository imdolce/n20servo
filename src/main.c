#include <ch32v00x.h>
#include <debug.h>

#define ADC_INPUT_GPIO_PORT GPIOA
#define ADC_INPUT_GPIO_PIN GPIO_Pin_2
#define ADC_INPUT_CHANNEL ADC_Channel_0

#define ADC_AVERAGE_SAMPLES 16U
#define ADC_FULL_SCALE_COUNTS 1023U
#define ADC_REFERENCE_MV 5000U
#define ADC_UPDATE_INTERVAL_MS 10U
#define ANGLE_FULL_SCALE_DEGREES 330U
#define UART_BAUD_RATE 921600U

#define TEST_MODE_ADC_ONLY 1U
#define TEST_MODE_MOTOR_AND_ADC 0U
#ifndef TEST_MODE
#define TEST_MODE TEST_MODE_MOTOR_AND_ADC
#endif

#define MOTOR_REVERSE_BRAKE_MS 50U
#define SWEEP_LOW_TARGET_TENTHS 200U
#define SWEEP_HIGH_TARGET_TENTHS 3100U
#define SWEEP_TARGET_TOLERANCE_TENTHS 30U

#define MOTOR_GPIO_PORT GPIOC
#define MOTOR_PC1_PIN GPIO_Pin_1
#define MOTOR_PC2_PIN GPIO_Pin_2
#define MOTOR_GPIO_PINS (MOTOR_PC1_PIN | MOTOR_PC2_PIN)

#define MOTOR_TOWARD_HIGH_PIN MOTOR_PC1_PIN
#define MOTOR_TOWARD_LOW_PIN MOTOR_PC2_PIN

typedef enum { SWEEP_TOWARD_LOW = 0, SWEEP_TOWARD_HIGH = 1 } SweepDirection;

void NMI_Handler(void) __attribute__((interrupt("WCH-Interrupt-fast")));
void HardFault_Handler(void) __attribute__((interrupt("WCH-Interrupt-fast")));

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

static uint32_t adc_to_angle_tenths(uint16_t adc_count) {
  return ((uint32_t)adc_count * ANGLE_FULL_SCALE_DEGREES * 10U +
          (ADC_FULL_SCALE_COUNTS / 2U)) /
         ADC_FULL_SCALE_COUNTS;
}

#if TEST_MODE == TEST_MODE_MOTOR_AND_ADC
static void motor_outputs_init(void) {
  GPIO_InitTypeDef GPIO_InitStructure = {0};

  RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOC, ENABLE);

  GPIO_InitStructure.GPIO_Pin = MOTOR_GPIO_PINS;
  GPIO_InitStructure.GPIO_Mode = GPIO_Mode_Out_PP;
  GPIO_InitStructure.GPIO_Speed = GPIO_Speed_30MHz;
  GPIO_Init(MOTOR_GPIO_PORT, &GPIO_InitStructure);
  GPIO_ResetBits(MOTOR_GPIO_PORT, MOTOR_GPIO_PINS);
}

static void motor_drive_pin(uint16_t active_pin) {
  GPIO_ResetBits(MOTOR_GPIO_PORT, MOTOR_GPIO_PINS);
  GPIO_SetBits(MOTOR_GPIO_PORT, active_pin);
}

static void motor_stop(void) {
  GPIO_ResetBits(MOTOR_GPIO_PORT, MOTOR_GPIO_PINS);
}

static void motor_brake(void) {
  GPIO_SetBits(MOTOR_GPIO_PORT, MOTOR_GPIO_PINS);
}

static void motor_drive_toward_high(void) {
  motor_drive_pin(MOTOR_TOWARD_HIGH_PIN);
}

static void motor_drive_toward_low(void) {
  motor_drive_pin(MOTOR_TOWARD_LOW_PIN);
}
#endif

int main(void) {
  uint32_t sample_index = 0;
  uint32_t direction_changes = 0;

#if TEST_MODE == TEST_MODE_MOTOR_AND_ADC
  SweepDirection sweep_direction = SWEEP_TOWARD_LOW;
  uint8_t endpoint_armed = 1;
#endif

  SystemCoreClockUpdate();
  Delay_Init();

#if (SDI_PRINT == SDI_PR_OPEN)
  SDI_Printf_Enable();
#else
  USART_Printf_Init(UART_BAUD_RATE);
#endif

  adc_init_pa2_a0();

#if TEST_MODE == TEST_MODE_MOTOR_AND_ADC
  motor_outputs_init();
  motor_stop();

  uint32_t startup_angle_tenths =
      adc_to_angle_tenths(adc_read_average(ADC_AVERAGE_SAMPLES));
  uint32_t sweep_midpoint_tenths =
      (SWEEP_LOW_TARGET_TENTHS + SWEEP_HIGH_TARGET_TENTHS) / 2U;
  sweep_direction = (startup_angle_tenths < sweep_midpoint_tenths)
                        ? SWEEP_TOWARD_HIGH
                        : SWEEP_TOWARD_LOW;
#endif

  while (1) {
    uint16_t raw = adc_read_raw();
    uint16_t average = adc_read_average(ADC_AVERAGE_SAMPLES);
    uint32_t millivolts =
        ((uint32_t)average * ADC_REFERENCE_MV + (ADC_FULL_SCALE_COUNTS / 2U)) /
        ADC_FULL_SCALE_COUNTS;
    uint32_t percent_tenths =
        ((uint32_t)average * 1000U + (ADC_FULL_SCALE_COUNTS / 2U)) /
        ADC_FULL_SCALE_COUNTS;
    uint32_t angle_tenths = adc_to_angle_tenths(average);

#if TEST_MODE == TEST_MODE_MOTOR_AND_ADC
    if (sweep_direction == SWEEP_TOWARD_HIGH) {
      if (angle_tenths < sweep_midpoint_tenths) {
        endpoint_armed = 1;
      }

      if (endpoint_armed && angle_tenths >= (SWEEP_HIGH_TARGET_TENTHS -
                                             SWEEP_TARGET_TOLERANCE_TENTHS)) {
        motor_brake();
        Delay_Ms(MOTOR_REVERSE_BRAKE_MS);
        sweep_direction = SWEEP_TOWARD_LOW;
        endpoint_armed = 0;
        direction_changes++;
        motor_drive_toward_low();
      } else {
        motor_drive_toward_high();
      }
    } else {
      if (angle_tenths > sweep_midpoint_tenths) {
        endpoint_armed = 1;
      }

      if (endpoint_armed && angle_tenths <= (SWEEP_LOW_TARGET_TENTHS +
                                             SWEEP_TARGET_TOLERANCE_TENTHS)) {
        motor_brake();
        Delay_Ms(MOTOR_REVERSE_BRAKE_MS);
        sweep_direction = SWEEP_TOWARD_HIGH;
        endpoint_armed = 0;
        direction_changes++;
        motor_drive_toward_high();
      } else {
        motor_drive_toward_low();
      }
    }
#endif

    printf("%lu,%u,%u,%lu,%lu.%lu,%lu.%lu,%lu\r\n", sample_index++, raw,
           average, millivolts, percent_tenths / 10U, percent_tenths % 10U,
           angle_tenths / 10U, angle_tenths % 10U, direction_changes);

    Delay_Ms(ADC_UPDATE_INTERVAL_MS);
  }

  return 0;
}

void NMI_Handler(void) {}
void HardFault_Handler(void) {
  while (1) {
  }
}
