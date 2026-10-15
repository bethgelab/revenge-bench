package custom;
import robocode.*;
import robocode.util.Utils;
import java.awt.Color;

/**
 * MyTank - Advanced RoboCode bot with improved movement and targeting
 * Team Claude - Round 3
 */
public class MyTank extends AdvancedRobot {
    private double enemyBearing;
    private double enemyDistance;
    private double enemyEnergy = 100;
    private int direction = 1;
    private int moveDirection = 1;

    public void run() {
        // Set colors
        setBodyColor(Color.blue);
        setGunColor(Color.blue);
        setRadarColor(Color.black);
        setScanColor(Color.yellow);
        setBulletColor(Color.red);

        // Independent movement of gun and radar
        setAdjustGunForRobotTurn(true);
        setAdjustRadarForGunTurn(true);
        setAdjustRadarForRobotTurn(true);

        while (true) {
            // Circular movement pattern
            setAhead(40 * moveDirection);
            setTurnRight(90);
            
            // Spin radar to find enemies
            setTurnRadarRight(360);
            
            execute();
        }
    }

    public void onScannedRobot(ScannedRobotEvent e) {
        enemyBearing = e.getBearing();
        enemyDistance = e.getDistance();
        double enemyAbsoluteBearing = getHeading() + e.getBearing();
        
        // Energy drop detection for dodging
        double energyDrop = enemyEnergy - e.getEnergy();
        if (energyDrop > 0 && energyDrop <= 3) {
            // Enemy fired, change direction
            moveDirection *= -1;
            setAhead(100 * moveDirection);
        }
        enemyEnergy = e.getEnergy();

        // Predictive targeting
        double enemyVelocity = e.getVelocity();
        double deltaTime = enemyDistance / (20 - 3 * Math.min(enemyDistance / 200, 1));
        double predictedX = Math.sin(Math.toRadians(enemyAbsoluteBearing)) * (enemyDistance + enemyVelocity * deltaTime);
        double predictedY = Math.cos(Math.toRadians(enemyAbsoluteBearing)) * (enemyDistance + enemyVelocity * deltaTime);
        double predictedBearing = Math.toDegrees(Math.atan2(predictedX, predictedY));
        
        // Aim at predicted position
        double gunTurn = Utils.normalRelativeAngleDegrees(predictedBearing - getGunHeading());
        setTurnGunRight(gunTurn);

        // Fire power based on distance and energy
        double firePower = Math.min(3.0, Math.min(getEnergy() / 4, 1200 / enemyDistance));
        if (Math.abs(gunTurn) < 10) {
            setFire(firePower);
        }

        // Keep radar locked on enemy
        double radarTurn = Utils.normalRelativeAngleDegrees(enemyAbsoluteBearing - getRadarHeading());
        setTurnRadarRight(radarTurn);
    }

    public void onHitByBullet(HitByBulletEvent e) {
        // Perpendicular movement when hit
        setTurnRight(Utils.normalRelativeAngleDegrees(90 - (getHeading() - e.getHeading())));
        moveDirection *= -1;
        setAhead(100 * moveDirection);
    }

    public void onHitWall(HitWallEvent e) {
        // Reverse direction when hitting wall
        moveDirection *= -1;
        setAhead(100 * moveDirection);
    }

    public void onHitRobot(HitRobotEvent e) {
        // Ram and fire when hitting enemy
        if (e.isMyFault()) {
            setTurnRight(Utils.normalRelativeAngleDegrees(e.getBearing()));
            setFire(3);
        }
    }
}