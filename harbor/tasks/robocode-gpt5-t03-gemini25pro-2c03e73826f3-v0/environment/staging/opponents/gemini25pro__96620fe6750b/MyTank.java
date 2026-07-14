package custom;

import robocode.*;
import java.awt.Color;
import java.awt.geom.Point2D; // Using Point2D for vector calculations
import robocode.util.Utils;

public class MyTank extends AdvancedRobot {

    private byte moveDirection = 1;
    private double lastEnemyEnergy = 100;

    public void run() {
        setBodyColor(new Color(128, 0, 128)); // Purple
        setGunColor(new Color(0, 0, 0));      // Black
        setRadarColor(new Color(255, 255, 0)); // Yellow
        setBulletColor(new Color(255, 165, 0)); // Orange

        setAdjustGunForRobotTurn(true);
        setAdjustRadarForGunTurn(true);

        while (true) {
            // Keep the radar spinning if we don't have a lock
            if (getRadarTurnRemaining() == 0.0) {
                setTurnRadarRight(Double.POSITIVE_INFINITY);
            }
            execute();
        }
    }

    public void onScannedRobot(ScannedRobotEvent e) {
        // --- Radar Lock ---
        // Tries to keep the radar locked on the enemy
        double radarTurn = getHeadingRadians() + e.getBearingRadians() - getRadarHeadingRadians();
        setTurnRadarRightRadians(Utils.normalRelativeAngle(radarTurn) * 1.5); // A little extra to keep lock

        // --- Linear Targeting ---
        // Calculate firepower based on distance and our energy
        // A more dynamic firepower calculation
        double distance = e.getDistance();
        double power = (400 / distance);
        double bulletPower = Math.min(power, 3.0);
        
        // Conserve energy when low
        if (getEnergy() < 25) {
            bulletPower = Math.min(bulletPower, getEnergy() / 5);
        }

 
        // Conserve energy with a finishing shot if enemy is low
        if (e.getEnergy() < 5) {
            bulletPower = Math.min(bulletPower, e.getEnergy() / 4);
        }

        double myX = getX();
        double myY = getY();
        double absoluteBearing = getHeadingRadians() + e.getBearingRadians();
        double enemyX = myX + e.getDistance() * Math.sin(absoluteBearing);
        double enemyY = myY + e.getDistance() * Math.cos(absoluteBearing);
        double enemyVelocity = e.getVelocity();
        double enemyHeading = e.getHeadingRadians();

        double deltaTime = 0;
        double battleFieldHeight = getBattleFieldHeight();
        double battleFieldWidth = getBattleFieldWidth();
        double predictedX = enemyX, predictedY = enemyY;

        // Predict enemy's future position
        while ((++deltaTime) * (20.0 - 3.0 * bulletPower) < Point2D.distance(myX, myY, predictedX, predictedY)) {
            predictedX += enemyVelocity * Math.sin(enemyHeading);
            predictedY += enemyVelocity * Math.cos(enemyHeading);

            // Wall smoothing for prediction
            if (predictedX < 18.0 || predictedY < 18.0 || predictedX > battleFieldWidth - 18.0 || predictedY > battleFieldHeight - 18.0) {
                predictedX = Math.min(Math.max(18.0, predictedX), battleFieldWidth - 18.0);
                predictedY = Math.min(Math.max(18.0, predictedY), battleFieldHeight - 18.0);
                break;
            }
        }
        double theta = Utils.normalAbsoluteAngle(Math.atan2(predictedX - getX(), predictedY - getY()));
        setTurnGunRightRadians(Utils.normalRelativeAngle(theta - getGunHeadingRadians()));
        
        // --- Firing ---
        if (getGunHeat() == 0 && Math.abs(getGunTurnRemaining()) < (150 / distance) && getEnergy() > bulletPower) {
            setFire(bulletPower);
        }

        // --- Evasive Movement (Oscillating) ---
        // Stay perpendicular to the enemy and move back and forth
        double turn = e.getBearingRadians() + Math.PI / 2;
        turn -= moveDirection * (0.2 + (Math.random() * 0.1)); // This creates the oscillating effect
        setTurnRightRadians(Utils.normalRelativeAngle(turn));
        setAhead((e.getDistance() / 4 + 25) * moveDirection);
        
        // --- Smart Reversal ---
        // Reverse direction when the enemy fires. A drop in energy indicates a fired shot.
        double energyDrop = lastEnemyEnergy - e.getEnergy();
        if (energyDrop > 1 && energyDrop <= 3 && Math.random() > 0.2) { // 80% chance to reverse
            moveDirection *= -1;
        }
        lastEnemyEnergy = e.getEnergy();
    }

    @Override
    public void onHitByBullet(HitByBulletEvent e) {
        System.out.println("OUCH! I was hit!");
        // When hit, reverse direction to dodge subsequent shots
        moveDirection *= -1;
    }

    @Override
    public void onHitWall(HitWallEvent e) {
        // Reverse direction if we hit a wall
        moveDirection *= -1;
    }
}