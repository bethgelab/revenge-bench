package custom;
import robocode.AdvancedRobot;
import robocode.ScannedRobotEvent;
import robocode.HitByBulletEvent;
import robocode.HitWallEvent;
import java.awt.Color;

/**
 * MyTank - improved Robocode bot
 * - Uses linear (lead) targeting to predict enemy position
 * - Locks radar on target by turning radar with the gun
 * - Improved movement: circles the enemy and changes direction when hit or close
 * - Fixes previous back/ahead inconsistencies
 */
public class MyTank extends AdvancedRobot {
    private int direction = 1;

    public void run() {
        // Set nice colors
        setBodyColor(Color.DARK_GRAY);
        setGunColor(Color.BLACK);
        setRadarColor(Color.ORANGE);
        setBulletColor(Color.YELLOW);
        setScanColor(Color.CYAN);

        // Independent movement
        setAdjustGunForRobotTurn(true);
        setAdjustRadarForGunTurn(true);
        setAdjustRadarForRobotTurn(true);

        // Start moving
        setAhead(100 * direction);
        setTurnRight(20);

        // Continuous loop: spin gun slowly initially to find enemies
        while (true) {
            // Keep radar scanning by turning the gun (radar is adjusted for gun turn)
            setTurnGunRight(360);
            execute();
        }
    }

    public void onScannedRobot(ScannedRobotEvent e) {
        // Absolute bearing to the enemy (degrees)
        double absoluteBearingDeg = getHeading() + e.getBearing();
        double absoluteBearing = Math.toRadians(absoluteBearingDeg);

        // Enemy current position
        double enemyX = getX() + Math.sin(absoluteBearing) * e.getDistance();
        double enemyY = getY() + Math.cos(absoluteBearing) * e.getDistance();

        // Choose fire power based on distance
        double firePower = Math.min(400.0 / e.getDistance(), 3.0);
        double bulletSpeed = 20 - 3 * firePower;

        // Predict future position using linear targeting (iterative)
        double enemyHeading = Math.toRadians(e.getHeading());
        double enemyVelocity = e.getVelocity();
        double predictedX = enemyX;
        double predictedY = enemyY;

        for (int i = 0; i < 20; i++) {
            double dx = predictedX - getX();
            double dy = predictedY - getY();
            double distance = Math.hypot(dx, dy);
            double time = distance / bulletSpeed;
            predictedX = enemyX + Math.sin(enemyHeading) * enemyVelocity * time;
            predictedY = enemyY + Math.cos(enemyHeading) * enemyVelocity * time;

            // If predicted point is outside battlefield, clamp and break
            double battlefieldWidth = getBattleFieldWidth();
            double battlefieldHeight = getBattleFieldHeight();
            if (predictedX < 18) { predictedX = 18; break; }
            if (predictedY < 18) { predictedY = 18; break; }
            if (predictedX > battlefieldWidth - 18) { predictedX = battlefieldWidth - 18; break; }
            if (predictedY > battlefieldHeight - 18) { predictedY = battlefieldHeight - 18; break; }
        }

        // Aim gun to predicted position
        double angleToPredicted = Math.toDegrees(Math.atan2(predictedX - getX(), predictedY - getY()));
        double gunTurnDeg = normalizeBearing(angleToPredicted - getGunHeading());
        setTurnGunRight(gunTurnDeg);

        // Lock radar by turning it the same as gun (keeps enemy scanned)
        double radarTurnDeg = normalizeBearing(absoluteBearingDeg - getRadarHeading());
        // Slightly overshoot to maintain lock
        setTurnRadarRight(radarTurnDeg + Math.signum(radarTurnDeg) * 2);

        // Fire only when gun is roughly aligned
        if (Math.abs(gunTurnDeg) < 12 && getEnergy() > 0.2) {
            setFire(firePower);
        }

        // Movement: circle the enemy. If very close, change direction abruptly.
        if (e.getDistance() < 150) {
            direction = -direction;
            setAhead(150 * direction);
            setTurnRight(e.getBearing() + 90); // try to circle perpendicularly
        } else {
            // Smooth circling with slight oscillation to be less predictable
            double orbit = 90 - 20 * direction;
            setTurnRight(e.getBearing() + orbit);
            setAhead(100 * direction);
        }
    }

    public void onHitByBullet(HitByBulletEvent e) {
        // Reverse direction and make an evasive move
        direction = -direction;
        setAhead(150 * direction);
        setTurnRight(90 - e.getBearing());
    }

    public void onHitWall(HitWallEvent e) {
        // Bounce off the wall and change direction
        direction = -direction;
        setBack(100);
        setTurnRight(90);
    }

    // Normalize an angle to the range [-180,180]
    private double normalizeBearing(double angle) {
        while (angle > 180) angle -= 360;
        while (angle < -180) angle += 360;
        return angle;
    }
}