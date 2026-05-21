package custom;
import robocode.AdvancedRobot;
import robocode.ScannedRobotEvent;
import robocode.util.Utils;

import java.awt.*;

public class MyTank extends AdvancedRobot {

    private int moveDirection = 1; // 1 for forward, -1 for backward
    private double oldEnemyHeading = 0;

    public void run() {
        setBodyColor(Color.blue);
        setGunColor(Color.white);
        setRadarColor(Color.red);
        setScanColor(Color.white);
        setBulletColor(Color.red);

        // Allow gun and radar to move independently of the body
        setAdjustGunForRobotTurn(true);
        setAdjustRadarForGunTurn(true);

        // Spin the radar to find a target
        while (true) {
            setTurnRadarRight(360);
            execute();
        }
    }

    public void onScannedRobot(ScannedRobotEvent e) {
        // Use radians for calculations
        double absoluteBearing = getHeadingRadians() + e.getBearingRadians();
        
        // --- Radar Lock ---
        // Keep the radar locked on the enemy.
        setTurnRadarRightRadians(Utils.normalRelativeAngle(absoluteBearing - getRadarHeadingRadians()) * 2);

        // --- Evasive Movement ---
        if (Math.random() < 0.05) { moveDirection *= -1; }

        // Always stay perpendicular to the enemy, but vary the angle slightly based on direction
        setTurnRight(e.getBearing() + 90 - (10 * moveDirection));
        setAhead((100 + Math.random() * 50) * moveDirection);

        // --- Targeting ---
        double firePower = Math.min(500 / e.getDistance(), 3);
        double distance = e.getDistance();
        double bulletSpeed = 20 - 3 * firePower;

        double theta;
        if (distance < 150) {
            // --- Linear Predictive Targeting for close enemies ---
            double enemyHeading = e.getHeadingRadians();
            double enemyVelocity = e.getVelocity();
            double deltaTime = distance / bulletSpeed;
            
            double enemyX = getX() + Math.sin(absoluteBearing) * distance;
            double enemyY = getY() + Math.cos(absoluteBearing) * distance;

            double futureX = enemyX + Math.sin(enemyHeading) * enemyVelocity * deltaTime;
            double futureY = enemyY + Math.cos(enemyHeading) * enemyVelocity * deltaTime;

            theta = Utils.normalAbsoluteAngle(Math.atan2(futureX - getX(), futureY - getY()));
        } else {
            // Circular predictive targeting
            double enemyHeading = e.getHeadingRadians();
            double enemyVelocity = e.getVelocity();

            // Calculate enemy's turn rate
            double enemyHeadingChange = Utils.normalRelativeAngle(enemyHeading - oldEnemyHeading);
            
            // This update is for the NEXT onScannedRobot event
            oldEnemyHeading = e.getHeadingRadians();

            double deltaTime = 0;
            double predictedX = getX() + e.getDistance() * Math.sin(absoluteBearing);
            double predictedY = getY() + e.getDistance() * Math.cos(absoluteBearing);
            
            while((++deltaTime * bulletSpeed) < Math.hypot(predictedX - getX(), predictedY - getY())) {
                predictedX += Math.sin(enemyHeading) * enemyVelocity;
                predictedY += Math.cos(enemyHeading) * enemyVelocity;
                enemyHeading += enemyHeadingChange; // Assume constant turn rate
            }

            theta = Utils.normalAbsoluteAngle(Math.atan2(predictedX - getX(), predictedY - getY()));
        }

        // Turn the gun to the predicted position
        setTurnGunRightRadians(Utils.normalRelativeAngle(theta - getGunHeadingRadians()));

        // --- Firing ---
        // Fire when gun is cool and aimed
        if (getGunHeat() == 0 && Math.abs(getGunTurnRemaining()) < 10) {
            fire(firePower);
        }

        execute();
    }

    @Override
    public void onHitWall(robocode.HitWallEvent e) {
        moveDirection *= -1;
    }
}