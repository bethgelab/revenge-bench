package custom;
import robocode.AdvancedRobot;
import robocode.ScannedRobotEvent;
import robocode.HitByBulletEvent;
import robocode.HitWallEvent;
import robocode.Rules;
import java.awt.Color;

/**
 * MyTank - improved basic bot for RoboCode rounds.
 * Improvements in this edit:
 *  - Fixed atan2 argument order when aiming (was swapped).
 *  - Fire only when gun heat is low and we have enough energy.
 *  - Use gun-turn-remaining in radians for alignment check.
 *  - Slightly lower minimum firepower to conserve energy.
 */
public class MyTank extends AdvancedRobot {

    public void run() {
        // Colors
        setBodyColor(Color.DARK_GRAY);
        setGunColor(Color.BLACK);
        setRadarColor(Color.ORANGE);
        setBulletColor(Color.YELLOW);
        setScanColor(Color.CYAN);

        // Independent gun and radar movement
        setAdjustGunForRobotTurn(true);
        setAdjustRadarForGunTurn(true);

        // Initial radar sweep
        setTurnRadarRightRadians(Double.POSITIVE_INFINITY);

        // Main loop: keep moving slowly and circling
        while (true) {
            // small forward movement to avoid staying in place
            setAhead(150);
            // gentle turn to keep moving in arcs (makes movement less predictable)
            setTurnRight(30);
            // keep radar sweeping
            setTurnRadarRightRadians(Double.POSITIVE_INFINITY);
            execute();
        }
    }

    public void onScannedRobot(ScannedRobotEvent e) {
        // Adaptive firepower (conservative minimum)
        double rawPower = 400.0 / e.getDistance();
        double firePower = Math.min(3, Math.max(0.1, rawPower));
        // Never attempt to spend more energy than we have (keep a small reserve)
        firePower = Math.min(firePower, Math.max(0.1, getEnergy() - 0.1));

        // Compute absolute bearing to target (radians)
        double absoluteBearing = Math.toRadians(getHeading()) + Math.toRadians(e.getBearing());
        // Current enemy coordinates
        double enemyX = getX() + Math.sin(absoluteBearing) * e.getDistance();
        double enemyY = getY() + Math.cos(absoluteBearing) * e.getDistance();

        // Predictive targeting (linear)
        double enemyHeading = Math.toRadians(e.getHeading());
        double enemyVelocity = e.getVelocity();
        double predictedX = enemyX;
        double predictedY = enemyY;

        double bulletSpeed = Rules.getBulletSpeed(firePower);
        double time = 0;
        // iterate to predict where target will be when bullet arrives
        while (time * bulletSpeed < distance(getX(), getY(), predictedX, predictedY) && time < 100) {
            time += 1;
            predictedX += Math.sin(enemyHeading) * enemyVelocity;
            predictedY += Math.cos(enemyHeading) * enemyVelocity;
            // clamp predicted pos to battlefield (avoid aiming outside)
            predictedX = Math.max(18, Math.min(getBattleFieldWidth() - 18, predictedX));
            predictedY = Math.max(18, Math.min(getBattleFieldHeight() - 18, predictedY));
        }

        // Aim gun at predicted position
        // NOTE: atan2 expects (deltaY, deltaX)
        double aim = Math.atan2(predictedY - getY(), predictedX - getX());
        double gunTurn = normalizeBearing(aim - Math.toRadians(getGunHeading()));
        setTurnGunRightRadians(gunTurn);

        // Fire when gun is nearly aligned, gun is cooled, and we have enough energy
        boolean gunReady = Math.abs(getGunTurnRemainingRadians()) < 0.12; // ~7 degrees tolerance
        boolean cooled = getGunHeat() <= 0;
        if (gunReady && cooled && getEnergy() > firePower + 0.1) {
            setFire(firePower);
        }

        // Movement: strafe and circle around target to be harder to hit
        double strafeAngle = e.getBearing() + 90 - (15 * Math.signum(e.getVelocity()));
        setTurnRight(strafeAngle);
        setAhead(100);
        // Keep radar locked on target for continuous updates
        double radarTurn = normalizeBearing(Math.toRadians(getHeading() + e.getBearing()) - Math.toRadians(getRadarHeading()));
        setTurnRadarRightRadians(radarTurn * 2); // more aggressive radar turn to counter motion
        execute();
    }

    public void onHitByBullet(HitByBulletEvent e) {
        // Evade: change direction and move out
        setTurnRight(90 - e.getBearing());
        setAhead(100);
        execute();
    }

    public void onHitWall(HitWallEvent e) {
        // Reverse a bit and turn away from wall
        setBack(50);
        setTurnRight(90);
        execute();
    }

    // Utility: normalize to -PI .. PI
    private double normalizeBearing(double angle) {
        while (angle > Math.PI) angle -= 2 * Math.PI;
        while (angle < -Math.PI) angle += 2 * Math.PI;
        return angle;
    }

    private double distance(double x1, double y1, double x2, double y2) {
        double dx = x2 - x1;
        double dy = y2 - y1;
        return Math.hypot(dx, dy);
    }
}