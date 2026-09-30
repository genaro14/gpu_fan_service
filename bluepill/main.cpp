#include <Arduino.h>

/*
 * STM32F103C8T6 Blue Pill
 *
 * USB CDC fan controller
 *
 * USB commands:
 *
 *   PWM 0
 *   PWM 60
 *   PWM 130
 *   PWM 180
 *   PWM 230
 *   PWM 255
 *
 *   GET
 *   STATUS
 *
 * PWM output:
 *
 *   PA8 / TIM1_CH1
 *   25 kHz
 *
 * Safety:
 *
 *   - Starts at 100%
 *   - If no valid command is received for 10 seconds,
 *     fan returns to 100%
 */

#define FAN_PWM_PIN PA8

#define PWM_MAX 255

#define PWM_FREQUENCY 25000UL

#define FAILSAFE_TIMEOUT 10000UL

HardwareTimer *FanTimer = nullptr;

uint8_t currentPwm = PWM_MAX;
uint32_t lastCommand = 0;

String commandBuffer;


/*
 * Convert the 0-255 application value to the timer's
 * actual PWM compare value.
 *
 * Timer:
 *
 *   72 MHz / 25 kHz = 2880 counts
 */
uint32_t pwmToCompare(uint8_t pwm)
{
    const uint32_t period = 2880;

    return ((uint32_t)pwm * period) / PWM_MAX;
}


/*
 * Set the fan PWM.
 */
void setFanPwm(uint8_t pwm)
{
    currentPwm = pwm;

    uint32_t compare = pwmToCompare(pwm);

    FanTimer->setCaptureCompare(
        1,
        compare,
        TICK_COMPARE_FORMAT
    );
}


/*
 * Send current state.
 */
void sendStatus()
{
    uint32_t duty =
        ((uint32_t)currentPwm * 100) / PWM_MAX;

    Serial.print("PWM=");
    Serial.print(currentPwm);

    Serial.print(" DUTY=");
    Serial.print(duty);

    Serial.println("%");
}


/*
 * Process one complete command.
 */
void processCommand(String command)
{
    command.trim();

    if (command.length() == 0)
        return;


    /*
     * PWM <0-255>
     */
    if (command.startsWith("PWM "))
    {
        String valueString = command.substring(4);

        int value = valueString.toInt();

        /*
         * Validate the command more strictly than toInt()
         * so things such as "PWM abc" don't become PWM 0.
         */
        bool valid = true;

        if (value < 0 || value > 255)
            valid = false;

        for (size_t i = 0; i < valueString.length(); i++)
        {
            if (!isDigit(valueString[i]))
            {
                valid = false;
                break;
            }
        }

        if (!valid)
        {
            Serial.println("ERR PWM 0-255");
            return;
        }

        setFanPwm((uint8_t)value);

        lastCommand = millis();

        Serial.print("OK PWM=");
        Serial.println(currentPwm);

        return;
    }


    /*
     * GET
     */
    if (command == "GET")
    {
        Serial.print("PWM=");
        Serial.println(currentPwm);

        lastCommand = millis();

        return;
    }


    /*
     * STATUS
     */
    if (command == "STATUS")
    {
        sendStatus();

        lastCommand = millis();

        return;
    }


    /*
     * Explicit maximum/failsafe command.
     */
    if (command == "MAX")
    {
        setFanPwm(PWM_MAX);

        lastCommand = millis();

        Serial.println("OK PWM=255");

        return;
    }


    Serial.println("ERR UNKNOWN COMMAND");
}


/*
 * Read USB CDC input.
 */
void processUsb()
{
    while (Serial.available())
    {
        char c = Serial.read();

        /*
         * Command terminator.
         */
        if (c == '\r' || c == '\n')
        {
            if (commandBuffer.length() > 0)
            {
                processCommand(commandBuffer);
                commandBuffer = "";
            }

            continue;
        }


        /*
         * Prevent runaway input.
         */
        if (commandBuffer.length() < 63)
        {
            commandBuffer += c;
        }
        else
        {
            commandBuffer = "";

            Serial.println("ERR COMMAND TOO LONG");
        }
    }
}


void setup()
{
    /*
     * USB CDC.
     */
    Serial.begin(115200);


    /*
     * Configure PA8 / TIM1_CH1.
     *
     * STM32duino's HardwareTimer gives us direct hardware PWM
     * rather than software PWM.
     */
    FanTimer = new HardwareTimer(TIM1);

    FanTimer->setMode(
        1,
        TIMER_OUTPUT_COMPARE_PWM1,
        FAN_PWM_PIN
    );

    FanTimer->setOverflow(
        PWM_FREQUENCY,
        HERTZ_FORMAT
    );

    FanTimer->setCaptureCompare(
        1,
        pwmToCompare(PWM_MAX),
        TICK_COMPARE_FORMAT
    );

    FanTimer->resume();


    /*
     * Start in the safe state.
     */
    setFanPwm(PWM_MAX);

    lastCommand = millis();


    /*
     * Give USB CDC time to enumerate.
     */
    delay(1000);

    Serial.println("GPU FAN CONTROLLER READY");
    Serial.println("PWM=255");
}


void loop()
{
    processUsb();


    /*
     * FAILSAFE
     *
     * If the host stops sending commands for 10 seconds,
     * force maximum fan speed.
     */
    if ((millis() - lastCommand) >= FAILSAFE_TIMEOUT)
    {
        if (currentPwm != PWM_MAX)
        {
            setFanPwm(PWM_MAX);

            Serial.println("FAILSAFE PWM=255");
        }

        /*
         * Prevent repeatedly triggering the failsafe message.
         */
        lastCommand = millis();
    }

    delay(5);
}

