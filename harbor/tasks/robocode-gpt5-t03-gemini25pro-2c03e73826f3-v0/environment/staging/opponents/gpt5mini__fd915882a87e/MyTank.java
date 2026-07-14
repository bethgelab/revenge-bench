package custom;

import robocode.AdvancedRobot;
import robocode.ScannedRobotEvent;
import robocode.HitByBulletEvent;
import robocode.HitWallEvent;
import robocode.HitRobotEvent;
import robocode.BulletHitEvent;

import java.awt.Color;
import java.util.Random;

public class MyTank extends AdvancedRobot {
    private final Random rnd = new Random();
    private int direction = 1;
    private int moveCounter = 0;

    public void run() {
        // Set nice visible colors
        setColors(Color.BLACK, Color.RED, Color.YELLOW);
        setAdjustGunForRobotTurn(true);
        setAdjustRadarForGunTurn(true);
        setAdjustRadarForRobotTurn(true);

        // Start with continuous radar sweep
        setTurnRadarRight(Double.POSITIVE_INFINITY);
        execute();

        // Main loop: patrol with some randomness to avoid being predictable
        while (true) {
            // Keep radar sweeping continuously so onScannedRobot radar corrections can work reliably
            setTurnRadarRight(Double.POSITIVE_INFINITY);

            // Small random movement changes to avoid being an easy target
            if (rnd.nextInt(80) == 0) {
                setTurnRight(rnd.nextInt(120) - 60);
            }
            // Occasionally flip direction to avoid predictability
            if (rnd.nextInt(120) == 0) direction = -direction;

            // Keep moving
            setAhead(100 * direction);
            execute();
        }
    }

    public void onScannedRobot(ScannedRobotEvent e) {
        moveCounter++;
        // Compute absolute bearing to target
        double absoluteBearing = getHeading() + e.getBearing();
        double bearingRad = Math.toRadians(absoluteBearing);
        double enemyX = getX() + Math.sin(bearingRad) * e.getDistance();
        double enemyY = getY() + Math.cos(bearingRad) * e.getDistance();
        double enemyHeading = Math.toRadians(e.getHeading());
        double enemyVelocity = e.getVelocity();

        // Dynamic firepower: prefer higher power for closer targets and when energy allows
        double firePower = Math.max(0.5, Math.min(3.0, 200.0 / e.getDistance()));
        if (getEnergy() < 15) firePower = Math.min(firePower, 1.0);
        double bulletSpeed = 20 - 3 * firePower;
        if (bulletSpeed < 0.1) bulletSpeed = 0.1;

        // Estimate lateral velocity (useful to decide power and movement)
        double relativeHeading = Math.toRadians(e.getHeading() - absoluteBearing);
        double lateralVel = enemyVelocity * Math.sin(relativeHeading);

        // Iteratively predict future position (more iterations for better leading)
        double predictedX = enemyX;
        double predictedY = enemyY;
        // Increased iterations for better convergence on moving targets
        for (int i = 0; i < 20; i++) {
            double dx = predictedX - getX();
            double dy = predictedY - getY();
            double dist = Math.hypot(dx, dy);
            double time = dist / bulletSpeed;
            predictedX += Math.sin(enemyHeading) * enemyVelocity * time;
            predictedY += Math.cos(enemyHeading) * enemyVelocity * time;

            // Keep predicted point inside battlefield bounds roughly
            predictedX = Math.max(18, Math.min(getBattleFieldWidth() - 18, predictedX));
            predictedY = Math.max(18, Math.min(getBattleFieldHeight() - 18, predictedY));
        }

        double dx = predictedX - getX();
        double dy = predictedY - getY();
        // Robocode's coordinate system: atan2(dx, dy) gives angle relative to north
        double aimAngle = Math.toDegrees(Math.atan2(dx, dy));
        double gunTurn = normalizeBearing(aimAngle - getGunHeading());
        setTurnGunRight(gunTurn);

        double radarTurn = normalizeBearing(absoluteBearing - getRadarHeading());
        // Double radar turn to try to keep target locked
        setTurnRadarRight(radarTurn * 2);

        // Fire only when gun is very well aligned and gun is ready
        if (Math.abs(gunTurn) < 3 && getGunHeat() == 0) {
            double adjustedPower;
            if (Math.abs(lateralVel) > 2.0) {
                adjustedPower = Math.max(0.5, firePower * 0.7);
            } else {
                adjustedPower = firePower;
            }
            if (getEnergy() < 10) adjustedPower = Math.min(adjustedPower, 1.0);

            // Avoid firing at trivially small power
            if (adjustedPower >= 0.2) {
                setFire(adjustedPower);
            }
        }

        // Movement strategy: strafing + occasional reversals for unpredictability
        // Use moveCounter and lateral velocity to decide when to flip direction
        if (moveCounter % 20 == 0) {
            // flip occasionally to avoid being locked into a circling pattern
            if (rnd.nextBoolean() || Math.abs(lateralVel) > 2.5) {
                direction = -direction;
            }
        }

        if (e.getDistance() < 120) {
            // Close: back off and try to strafe
            setBack(60);
            setTurnRight(e.getBearing() + 90);
            setAhead(80 * direction);
        } else if (e.getDistance() < 350) {
            // Mid distance: circle the enemy to be a harder target
            setTurnRight(e.getBearing() + 90 - (10 * direction));
            setAhead(60 * direction);
        } else {
            // Far: approach slowly but keep scanning / respect direction to avoid walking into bullets
            setTurnRight(e.getBearing() + 10 * direction);
            setAhead(50 * direction);
        }

        // Simple wall-avoidance: if we're too close to the battlefield edge, reverse direction
        double margin = 60.0;
        if (getX() < margin || getY() < margin || getBattleFieldWidth() - getX() < margin || getBattleFieldHeight() - getY() < margin) {
            direction = -direction;
            // try to move away from the wall immediately
            setAhead(80 * direction);
            // small turn to avoid hugging the wall
            setTurnRight(30);
        }

        // Execute all queued actions at once
        execute();

        // Ask radar to scan again to help maintain lock in between turns
        scan();
    }

    public void onHitByBullet(HitByBulletEvent e) {
        // Evasive maneuver: turn perpendicular to incoming bullet bearing and move unpredictably
        // Add some randomness to make the response less predictable
        int randomTurn = rnd.nextInt(80) - 40;
        setTurnRight(90 - e.getBearing() + randomTurn);
        direction = -direction;
        setAhead(120);
        execute();
        // small random dodge
        if (rnd.nextBoolean()) {
            setTurnRight(rnd.nextInt(120) - 60);
            setAhead(40);
            execute();
        }
    }

    public void onHitWall(HitWallEvent e) {
        // Bounce off walls: reverse and try to get away from the wall
        direction = -direction;
        setBack(60);
        setTurnRight(45);
        setAhead(40);
        execute();
    }

    public void onHitRobot(HitRobotEvent e) {
        // If we collide, back off and fire a strong shot if the front hit
        if (e.isMyFault()) {
            setBack(50);
        }
        setTurnGunRight(normalizeBearing(e.getBearing() + getHeading() - getGunHeading()));
        setFire(Math.min(3.0, getEnergy() / 4.0 + 0.5));
        // Change direction to avoid staying stuck
        direction = -direction;
        setAhead(60 * direction);
        execute();
    }

    public void onBulletHit(BulletHitEvent e) {
        // Hit an enemy: be unpredictable and advance
        direction = (rnd.nextBoolean() ? 1 : -1);
        setAhead(60 * direction);
        setTurnRight(rnd.nextInt(120) - 60);
        execute();
    }

    // Normalize angle to the range [-180, 180]
    private double normalizeBearing(double angle) {
        while (angle > 180) angle -= 360;
        while (angle < -180) angle += 360;
        return angle;
    }
}